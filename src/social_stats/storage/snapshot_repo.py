"""Snapshot repository and mathematical delta calculator (1h and 24h windows)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from social_stats.models.api import HistoryPoint
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.database import Database

WINDOW_1H_SECONDS = 3600
TOLERANCE_1H_SECONDS = 1800

WINDOW_24H_SECONDS = 86400
TOLERANCE_24H_SECONDS = 14400


@dataclass(frozen=True)
class DeltaCalculationResult:
    """Result of computing 1h and 24h variations from historical snapshots."""

    followers_last_24h: int | None
    views_last_24h: int | None
    views_last_1h: int | None
    window_1h_complete: bool
    window_24h_complete: bool


class SnapshotRepository:
    """Manages time-series snapshots in SQLite and computes 1h / 24h deltas."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def _find_reference_snapshot(
        self,
        platform: str,
        account_key: str,
        now_ts: int,
        window_seconds: int,
        tolerance_seconds: int,
    ) -> tuple[dict[str, int | None] | None, bool]:
        """
        Look up reference snapshot for (now_ts - window_seconds).
        Returns (snapshot_row_dict, window_complete).
        1. Nominal: most recent snapshot in [target_ts - tolerance, target_ts].
        2. Warm-up: oldest snapshot in (target_ts, now_ts).
        3. None (cold start or after outage > window + tolerance).
        """
        target_ts = now_ts - window_seconds
        min_valid_ts = target_ts - tolerance_seconds

        async with self.db.conn.execute(
            """
            SELECT followers_total, views_total, posts_total, timestamp
            FROM metric_snapshots
            WHERE platform = ?
              AND account_key = ?
              AND timestamp <= ?
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT 1;
            """,
            (platform, account_key, target_ts, min_valid_ts),
        ) as cursor:
            nominal_row = await cursor.fetchone()

        if nominal_row is not None:
            return (
                {
                    "followers_total": nominal_row["followers_total"],
                    "views_total": nominal_row["views_total"],
                    "posts_total": nominal_row["posts_total"],
                    "timestamp": nominal_row["timestamp"],
                },
                True,
            )

        async with self.db.conn.execute(
            """
            SELECT followers_total, views_total, posts_total, timestamp
            FROM metric_snapshots
            WHERE platform = ?
              AND account_key = ?
              AND timestamp > ?
              AND timestamp < ?
            ORDER BY timestamp ASC
            LIMIT 1;
            """,
            (platform, account_key, target_ts, now_ts),
        ) as cursor:
            warmup_row = await cursor.fetchone()

        if warmup_row is not None:
            return (
                {
                    "followers_total": warmup_row["followers_total"],
                    "views_total": warmup_row["views_total"],
                    "posts_total": warmup_row["posts_total"],
                    "timestamp": warmup_row["timestamp"],
                },
                False,
            )

        return None, False

    async def calculate_deltas(
        self,
        platform: Platform | str,
        account_key: str,
        current_followers: int | None,
        current_views: int | None,
        now_ts: int | None = None,
    ) -> DeltaCalculationResult:
        """
        Compute Δ_1h (views_last_1h) and Δ_24h (followers_last_24h, views_last_24h).
        Must be executed BEFORE inserting the current snapshot at now_ts.
        """
        ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        norm_platform = str(platform).lower()

        ref_1h, complete_1h = await self._find_reference_snapshot(
            norm_platform,
            account_key,
            ts,
            WINDOW_1H_SECONDS,
            TOLERANCE_1H_SECONDS,
        )
        ref_24h, complete_24h = await self._find_reference_snapshot(
            norm_platform,
            account_key,
            ts,
            WINDOW_24H_SECONDS,
            TOLERANCE_24H_SECONDS,
        )

        # Compute views_last_1h
        views_last_1h: int | None = None
        if current_views is not None:
            if ref_1h is not None and ref_1h["views_total"] is not None:
                views_last_1h = current_views - ref_1h["views_total"]
            else:
                views_last_1h = 0

        # Compute followers_last_24h and views_last_24h
        followers_last_24h: int | None = None
        if current_followers is not None:
            if ref_24h is not None and ref_24h["followers_total"] is not None:
                followers_last_24h = current_followers - ref_24h["followers_total"]
            else:
                followers_last_24h = 0

        views_last_24h: int | None = None
        if current_views is not None:
            if ref_24h is not None and ref_24h["views_total"] is not None:
                views_last_24h = current_views - ref_24h["views_total"]
            else:
                views_last_24h = 0

        return DeltaCalculationResult(
            followers_last_24h=followers_last_24h,
            views_last_24h=views_last_24h,
            views_last_1h=views_last_1h,
            window_1h_complete=complete_1h,
            window_24h_complete=complete_24h,
        )

    async def insert_snapshot(
        self,
        platform: Platform | str,
        account_key: str,
        metrics: AccountMetrics,
        timestamp: int | None = None,
    ) -> None:
        """Insert a point-in-time metric snapshot into metric_snapshots."""
        ts = timestamp if timestamp is not None else int(datetime.now(UTC).timestamp())
        latest = metrics.latest_post
        extra_data: dict[str, Any] = {}
        if metrics.price_usd is not None:
            extra_data["price_usd"] = metrics.price_usd
        if metrics.price_eur is not None:
            extra_data["price_eur"] = metrics.price_eur
        extra_json = json.dumps(extra_data) if extra_data else None
        await self.db.execute_write(
            """
            INSERT INTO metric_snapshots (
                timestamp, platform, account_key,
                followers_total, posts_total, views_total,
                latest_post_id, latest_post_views, latest_post_likes,
                latest_post_comments, latest_post_shares, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                ts,
                str(platform).lower(),
                account_key,
                metrics.followers_total,
                metrics.posts_total,
                metrics.views_total,
                latest.post_id if latest else None,
                latest.views if latest else None,
                latest.likes if latest else None,
                latest.comments if latest else None,
                latest.shares if latest else None,
                extra_json,
            ),
        )

    async def enrich_and_record(
        self,
        platform: Platform | str,
        account_key: str,
        metrics: AccountMetrics,
        timestamp: int | None = None,
    ) -> AccountMetrics:
        """Calculate deltas against historical snapshots, enrich metrics, and save snapshot."""
        ts = timestamp if timestamp is not None else int(datetime.now(UTC).timestamp())
        deltas = await self.calculate_deltas(
            platform=platform,
            account_key=account_key,
            current_followers=metrics.followers_total,
            current_views=metrics.views_total,
            now_ts=ts,
        )
        enriched = metrics.model_copy(
            update={
                "followers_last_24h": deltas.followers_last_24h,
                "views_last_24h": deltas.views_last_24h,
                "views_last_1h": deltas.views_last_1h,
                "window_1h_complete": deltas.window_1h_complete,
                "window_24h_complete": deltas.window_24h_complete,
            }
        )
        await self.insert_snapshot(platform, account_key, enriched, timestamp=ts)
        return enriched

    async def get_history(
        self,
        platform: Platform | str,
        account_key: str,
        window_seconds: int,
        now_ts: int | None = None,
    ) -> list[HistoryPoint]:
        """Return ordered time-series snapshots for an account within [now - window, now]."""
        ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        min_ts = ts - window_seconds
        async with self.db.conn.execute(
            """
            SELECT timestamp, followers_total, posts_total, views_total,
                   latest_post_views, extra_json
            FROM metric_snapshots
            WHERE platform = ?
              AND account_key = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC;
            """,
            (str(platform).lower(), account_key, min_ts, ts),
        ) as cursor:
            rows = await cursor.fetchall()

        points: list[HistoryPoint] = []
        for row in rows:
            price_usd: float | None = None
            price_eur: float | None = None
            raw_extra = row["extra_json"]
            if raw_extra:
                try:
                    extra_dict = json.loads(raw_extra)
                    if isinstance(extra_dict, dict):
                        if extra_dict.get("price_usd") is not None:
                            price_usd = float(extra_dict["price_usd"])
                        if extra_dict.get("price_eur") is not None:
                            price_eur = float(extra_dict["price_eur"])
                except (ValueError, TypeError):
                    pass
            points.append(
                HistoryPoint(
                    timestamp=datetime.fromtimestamp(row["timestamp"], tz=UTC),
                    followers_total=row["followers_total"],
                    posts_total=row["posts_total"],
                    views_total=row["views_total"],
                    latest_post_views=row["latest_post_views"],
                    price_usd=price_usd,
                    price_eur=price_eur,
                )
            )
        return points

    async def prune_old_snapshots(
        self,
        retention_days: int = 30,
        now_ts: int | None = None,
    ) -> int:
        """Delete snapshots older than retention_days and run PRAGMA optimize."""
        ts = now_ts if now_ts is not None else int(datetime.now(UTC).timestamp())
        cutoff_ts = ts - (retention_days * 86400)
        async with self.db.write_lock:

            async def _do_prune() -> int:
                cursor = await self.db.conn.execute(
                    "DELETE FROM metric_snapshots WHERE timestamp < ?;",
                    (cutoff_ts,),
                )
                deleted = cursor.rowcount if cursor.rowcount is not None else 0
                await self.db.conn.execute("PRAGMA optimize;")
                await self.db.conn.commit()
                return deleted

            return await asyncio.shield(_do_prune())
