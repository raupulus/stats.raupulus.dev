"""SQLite database manager with WAL mode and schema initialization."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from social_stats.models.enums import CollectorStatus, Platform
from social_stats.models.metrics import AccountMetrics, AccountState

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    platform TEXT NOT NULL,
    account_key TEXT NOT NULL,
    followers_total INTEGER,
    posts_total INTEGER,
    views_total INTEGER,
    latest_post_id TEXT,
    latest_post_views INTEGER,
    latest_post_likes INTEGER,
    latest_post_comments INTEGER,
    latest_post_shares INTEGER,
    extra_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshots_lookup
ON metric_snapshots (platform, account_key, timestamp DESC);

CREATE TABLE IF NOT EXISTS account_latest_state (
    platform TEXT NOT NULL,
    account_key TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    last_attempt_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (platform, account_key)
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    provider TEXT NOT NULL,
    credentials_ref TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (provider, credentials_ref)
);
"""


@dataclass
class StoredAuthToken:
    """Represents an OAuth token persisted in SQLite auth_tokens."""

    provider: str
    credentials_ref: str
    access_token: str
    refresh_token: str | None
    expires_at: int | None
    updated_at: int


@dataclass
class PersistedAccountRecord:
    """Represents a row loaded from account_latest_state."""

    state: AccountState
    consecutive_failures: int


class Database:
    """Manages an asynchronous SQLite connection in WAL mode."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        """Return active connection or raise RuntimeError if not connected."""
        if self._conn is None:
            raise RuntimeError("Database connection has not been initialized. Call connect() first.")
        return self._conn

    async def connect(self) -> None:
        """Open connection, enable WAL mode, and initialize schema."""
        if self._conn is not None:
            return
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    async def close(self) -> None:
        """Close active SQLite connection."""
        async with self.write_lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None

    async def execute_write(
        self, sql: str, parameters: tuple[Any, ...] = ()
    ) -> int:
        """Execute a write statement and commit atomically under write_lock and shield."""
        async with self.write_lock:

            async def _do_write() -> int:
                cursor = await self.conn.execute(sql, parameters)
                rowcount = cursor.rowcount if cursor.rowcount is not None else 0
                await self.conn.commit()
                return rowcount

            return await asyncio.shield(_do_write())

    async def check_health(self) -> bool:
        """Execute lightweight SELECT 1 to verify SQLite responsiveness."""
        if self._conn is None:
            return False
        try:
            async with self._conn.execute("SELECT 1;") as cursor:
                row = await cursor.fetchone()
                return row is not None and row[0] == 1
        except Exception:
            return False

    async def upsert_latest_state(
        self,
        state: AccountState,
        consecutive_failures: int = 0,
    ) -> None:
        """Persist or update the latest state of an account in SQLite."""
        updated_ts = (
            int(state.last_updated_at.timestamp())
            if state.last_updated_at is not None
            else 0
        )
        attempt_ts = (
            int(state.last_attempt_at.timestamp())
            if state.last_attempt_at is not None
            else int(datetime.now(UTC).timestamp())
        )
        payload = state.metrics.model_dump(mode="json")
        payload_meta = {
            "handle": state.handle,
            "label": state.label,
            "metrics": payload,
        }
        await self.execute_write(
            """
            INSERT INTO account_latest_state (
                platform, account_key, updated_at, last_attempt_at,
                status, error_message, consecutive_failures, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, account_key) DO UPDATE SET
                updated_at = excluded.updated_at,
                last_attempt_at = excluded.last_attempt_at,
                status = excluded.status,
                error_message = excluded.error_message,
                consecutive_failures = excluded.consecutive_failures,
                payload_json = excluded.payload_json;
            """,
            (
                str(state.platform),
                state.account_key,
                updated_ts,
                attempt_ts,
                str(state.status),
                state.error_message,
                consecutive_failures,
                json.dumps(payload_meta),
            ),
        )

    async def load_all_latest_states(self) -> dict[tuple[Platform, str], PersistedAccountRecord]:
        """Load all persisted account states on container startup."""
        records: dict[tuple[Platform, str], PersistedAccountRecord] = {}
        async with self.conn.execute(
            """
            SELECT platform, account_key, updated_at, last_attempt_at,
                   status, error_message, consecutive_failures, payload_json
            FROM account_latest_state;
            """
        ) as cursor:
            rows = await cursor.fetchall()

        for row in rows:
            try:
                platform = Platform(row["platform"])
                status = CollectorStatus(row["status"])
                raw_payload = json.loads(row["payload_json"])
                if "metrics" in raw_payload and isinstance(raw_payload["metrics"], dict):
                    metrics = AccountMetrics.model_validate(raw_payload["metrics"])
                    handle = raw_payload.get("handle")
                    label = raw_payload.get("label")
                else:
                    metrics = AccountMetrics.model_validate(raw_payload)
                    handle = None
                    label = None

                updated_at = (
                    datetime.fromtimestamp(row["updated_at"], tz=UTC)
                    if row["updated_at"] > 0
                    else None
                )
                last_attempt_at = (
                    datetime.fromtimestamp(row["last_attempt_at"], tz=UTC)
                    if row["last_attempt_at"] > 0
                    else None
                )
                state = AccountState(
                    platform=platform,
                    account_key=row["account_key"],
                    handle=handle,
                    label=label,
                    status=status,
                    last_updated_at=updated_at,
                    last_attempt_at=last_attempt_at,
                    error_message=row["error_message"],
                    metrics=metrics,
                )
                records[(platform, row["account_key"])] = PersistedAccountRecord(
                    state=state,
                    consecutive_failures=int(row["consecutive_failures"]),
                )
            except Exception:
                continue

        return records

    async def get_auth_token(
        self, provider: str, credentials_ref: str = "MAIN"
    ) -> StoredAuthToken | None:
        """Retrieve a persisted auto-refreshing OAuth token."""
        async with self.conn.execute(
            """
            SELECT provider, credentials_ref, access_token, refresh_token, expires_at, updated_at
            FROM auth_tokens
            WHERE provider = ? AND credentials_ref = ?;
            """,
            (provider.lower(), credentials_ref.upper()),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return StoredAuthToken(
            provider=row["provider"],
            credentials_ref=row["credentials_ref"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=row["expires_at"],
            updated_at=row["updated_at"],
        )

    async def upsert_auth_token(
        self,
        provider: str,
        credentials_ref: str,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: int | None = None,
        now_ts: int | None = None,
    ) -> None:
        """Save or update an auto-refreshing OAuth token in SQLite."""
        updated = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        await self.execute_write(
            """
            INSERT INTO auth_tokens (
                provider, credentials_ref, access_token, refresh_token, expires_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, credentials_ref) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at,
                updated_at = excluded.updated_at;
            """,
            (
                provider.lower(),
                credentials_ref.upper(),
                access_token,
                refresh_token,
                expires_at,
                updated,
            ),
        )
