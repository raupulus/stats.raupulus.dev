"""In-memory state store and diff engine for account metrics and health status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from social_stats.config.profiles import AccountConfig, ProfilesRegistry
from social_stats.models.api import MetricChange
from social_stats.models.enums import CollectorStatus, Platform
from social_stats.models.metrics import AccountMetrics, AccountState
from social_stats.storage.database import Database

TOP_LEVEL_METRIC_FIELDS: tuple[str, ...] = (
    "followers_total",
    "followers_last_24h",
    "posts_total",
    "views_total",
    "views_last_24h",
    "views_last_1h",
    "stars_total",
    "forks_total",
    "live_viewers",
    "pulsations_total",
    "pulsations_today",
    "pulsations_last_1h",
    "clicks_total",
    "clicks_today",
    "clicks_last_1h",
)

CRYPTO_METRIC_FIELDS: tuple[str, ...] = (
    "price_usd",
    "price_eur",
    "price_change_24h_pct",
    "price_change_24h_eur_pct",
)

DELTA_METRIC_FIELDS: frozenset[str] = frozenset(
    {"followers_last_24h", "views_last_24h", "views_last_1h"}
)

LATEST_POST_METRIC_FIELDS: tuple[str, ...] = (
    "views",
    "likes",
    "comments",
    "shares",
)


@dataclass(frozen=True)
class DiffResult:
    """Result of comparing incoming AccountMetrics with previous cached metrics."""

    is_new_latest_post: bool
    changes: dict[str, MetricChange]

    @property
    def has_changes(self) -> bool:
        """Return True if any numeric metric changed or a new post was detected."""
        return bool(self.changes) or self.is_new_latest_post


@dataclass(frozen=True)
class StatusTransition:
    """Represents a collector status change for an account."""

    platform: Platform
    account_key: str
    previous_status: CollectorStatus
    current_status: CollectorStatus
    last_updated_at: datetime | None
    error_message: str | None


@dataclass(frozen=True)
class AccountUpdateOutcome:
    """Returned by StateStore when an account's metrics are updated."""

    state: AccountState
    diff: DiffResult
    status_transition: StatusTransition | None
    consecutive_failures: int


class DiffEngine:
    """Computes granular changes between two AccountMetrics snapshots."""

    @staticmethod
    def compute_diff(
        previous: AccountMetrics | None,
        current: AccountMetrics,
    ) -> DiffResult:
        """Compare previous and current metrics, handling new latest_post IDs safely."""
        changes: dict[str, MetricChange] = {}

        for field in TOP_LEVEL_METRIC_FIELDS:
            curr_val: int | None = getattr(current, field)
            if curr_val is None:
                continue
            prev_val: int | None = getattr(previous, field) if previous is not None else None
            if prev_val is None:
                if field in DELTA_METRIC_FIELDS and curr_val == 0:
                    continue
                changes[field] = MetricChange(previous=None, current=curr_val, delta=curr_val)
            elif curr_val != prev_val:
                changes[field] = MetricChange(
                    previous=prev_val,
                    current=curr_val,
                    delta=curr_val - prev_val,
                )

        for cfield in CRYPTO_METRIC_FIELDS:
            curr_fval: float | None = getattr(current, cfield)
            if curr_fval is None:
                continue
            prev_fval: float | None = (
                getattr(previous, cfield) if previous is not None else None
            )
            if prev_fval is None:
                changes[cfield] = MetricChange(
                    previous=None,
                    current=curr_fval,
                    delta=curr_fval,
                )
            elif curr_fval != prev_fval:
                changes[cfield] = MetricChange(
                    previous=prev_fval,
                    current=curr_fval,
                    delta=round(curr_fval - prev_fval, 8),
                )

        if current.is_live is not None:
            curr_live_int = 1 if current.is_live else 0
            prev_live_bool = previous.is_live if previous is not None else None
            if prev_live_bool is None:
                if current.is_live:
                    changes["is_live"] = MetricChange(previous=None, current=1, delta=1)
            elif current.is_live != prev_live_bool:
                prev_live_int = 1 if prev_live_bool else 0
                changes["is_live"] = MetricChange(
                    previous=prev_live_int,
                    current=curr_live_int,
                    delta=curr_live_int - prev_live_int,
                )

        is_new_latest_post = False
        curr_post = current.latest_post
        prev_post = previous.latest_post if previous is not None else None

        if curr_post is not None:
            if (
                prev_post is not None
                and curr_post.post_id is not None
                and prev_post.post_id != curr_post.post_id
            ):
                is_new_latest_post = True
                for pfield in LATEST_POST_METRIC_FIELDS:
                    c_val: int | None = getattr(curr_post, pfield)
                    if c_val is not None:
                        changes[f"latest_post.{pfield}"] = MetricChange(
                            previous=0,
                            current=c_val,
                            delta=c_val,
                        )
            elif prev_post is None:
                if previous is not None and curr_post.post_id is not None:
                    is_new_latest_post = True
                baseline = 0 if is_new_latest_post else None
                for pfield in LATEST_POST_METRIC_FIELDS:
                    c_val = getattr(curr_post, pfield)
                    if c_val is not None:
                        changes[f"latest_post.{pfield}"] = MetricChange(
                            previous=baseline,
                            current=c_val,
                            delta=c_val,
                        )
            else:
                for pfield in LATEST_POST_METRIC_FIELDS:
                    c_val = getattr(curr_post, pfield)
                    p_val: int | None = getattr(prev_post, pfield)
                    if c_val is not None and c_val != p_val:
                        delta = c_val - (p_val if p_val is not None else 0)
                        changes[f"latest_post.{pfield}"] = MetricChange(
                            previous=p_val,
                            current=c_val,
                            delta=delta,
                        )

        return DiffResult(is_new_latest_post=is_new_latest_post, changes=changes)


class StateStore:
    """Async-safe in-memory store of account states backed by SQLite persistence."""

    def __init__(self, db: Database | None = None) -> None:
        self.db = db
        self._lock = asyncio.Lock()
        self._states: dict[tuple[Platform, str], AccountState] = {}
        self._failures: dict[tuple[Platform, str], int] = {}

    async def initialize_from_config_and_db(self, registry: ProfilesRegistry) -> None:
        """Seed store from config/profiles.yaml and hydrate with SQLite account_latest_state."""
        persisted = await self.db.load_all_latest_states() if self.db is not None else {}

        async with self._lock:
            for profile in registry.profiles.values():
                for platform_str, accounts in profile.accounts.items():
                    platform = Platform(platform_str)
                    for acc in accounts:
                        key = (platform, acc.account_key)
                        if not acc.enabled:
                            self._states[key] = AccountState(
                                platform=platform,
                                account_key=acc.account_key,
                                handle=acc.handle,
                                label=acc.label,
                                status=CollectorStatus.DISABLED,
                            )
                            self._failures[key] = 0
                            continue

                        if key in persisted:
                            from social_stats.collectors.base import sanitize_error_message

                            record = persisted[key]
                            safe_err = (
                                sanitize_error_message(record.state.error_message)
                                if record.state.error_message
                                else None
                            )
                            restored = record.state.model_copy(
                                update={
                                    "handle": acc.handle or record.state.handle,
                                    "label": acc.label or record.state.label,
                                    "error_message": safe_err,
                                }
                            )
                            self._states[key] = restored
                            self._failures[key] = record.consecutive_failures
                        elif key not in self._states:
                            self._states[key] = AccountState(
                                platform=platform,
                                account_key=acc.account_key,
                                handle=acc.handle,
                                label=acc.label,
                                status=CollectorStatus.HEALTHY,
                            )
                            self._failures[key] = 0

    def get_account_state(self, platform: Platform | str, account_key: str) -> AccountState | None:
        """Return current in-memory AccountState for (platform, account_key) in O(1)."""
        p = Platform(str(platform).lower())
        return self._states.get((p, account_key))

    def get_all_states(self) -> dict[tuple[Platform, str], AccountState]:
        """Return shallow copy of all account states."""
        return dict(self._states)

    def get_consecutive_failures(self, platform: Platform | str, account_key: str) -> int:
        """Return consecutive failure count for (platform, account_key)."""
        p = Platform(str(platform).lower())
        return self._failures.get((p, account_key), 0)

    async def update_account_success(
        self,
        platform: Platform | str,
        account_key: str,
        metrics: AccountMetrics,
        *,
        handle: str | None = None,
        label: str | None = None,
        now: datetime | None = None,
    ) -> AccountUpdateOutcome:
        """Update an account with fresh metrics, compute diff, and persist to SQLite."""
        ts = now if now is not None else datetime.now(UTC)
        p = Platform(str(platform).lower())
        key = (p, account_key)

        async with self._lock:
            prev_state = self._states.get(key)
            prev_metrics = (
                prev_state.metrics
                if (prev_state is not None and prev_state.last_updated_at is not None)
                else None
            )
            diff = DiffEngine.compute_diff(prev_metrics, metrics)

            prev_status = prev_state.status if prev_state is not None else None
            new_state = AccountState(
                platform=p,
                account_key=account_key,
                handle=handle if handle is not None else (prev_state.handle if prev_state else None),
                label=label if label is not None else (prev_state.label if prev_state else None),
                status=CollectorStatus.HEALTHY,
                last_updated_at=ts,
                last_attempt_at=ts,
                error_message=None,
                metrics=metrics,
            )
            self._states[key] = new_state
            self._failures[key] = 0

            transition: StatusTransition | None = None
            if (
                prev_state is not None
                and prev_state.last_attempt_at is not None
                and prev_status is not None
                and prev_status != CollectorStatus.HEALTHY
            ):
                transition = StatusTransition(
                    platform=p,
                    account_key=account_key,
                    previous_status=prev_status,
                    current_status=CollectorStatus.HEALTHY,
                    last_updated_at=ts,
                    error_message=None,
                )

            if self.db is not None:
                await self.db.upsert_latest_state(new_state, consecutive_failures=0)

            return AccountUpdateOutcome(
                state=new_state,
                diff=diff,
                status_transition=transition,
                consecutive_failures=0,
            )

    async def record_account_failure(
        self,
        platform: Platform | str,
        account_key: str,
        error_message: str,
        *,
        account_config: AccountConfig | None = None,
        now: datetime | None = None,
    ) -> tuple[AccountState, StatusTransition | None, int]:
        """
        Mark an account failed while preserving any valid cached metrics as STALE.
        If no prior metrics exist, status is set to ERROR.
        """
        from social_stats.collectors.base import sanitize_error_message

        safe_error = sanitize_error_message(error_message)
        ts = now if now is not None else datetime.now(UTC)
        p = Platform(str(platform).lower())
        key = (p, account_key)

        async with self._lock:
            prev_state = self._states.get(key)
            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures

            has_valid_cache = prev_state is not None and prev_state.last_updated_at is not None
            target_status = CollectorStatus.STALE if has_valid_cache else CollectorStatus.ERROR
            prev_status = prev_state.status if prev_state is not None else CollectorStatus.HEALTHY

            if prev_state is not None:
                new_state = prev_state.model_copy(
                    update={
                        "status": target_status,
                        "last_attempt_at": ts,
                        "error_message": safe_error,
                    }
                )
            else:
                new_state = AccountState(
                    platform=p,
                    account_key=account_key,
                    handle=account_config.handle if account_config else None,
                    label=account_config.label if account_config else None,
                    status=target_status,
                    last_updated_at=None,
                    last_attempt_at=ts,
                    error_message=safe_error,
                )

            self._states[key] = new_state

            transition: StatusTransition | None = None
            if prev_status != target_status:
                transition = StatusTransition(
                    platform=p,
                    account_key=account_key,
                    previous_status=prev_status,
                    current_status=target_status,
                    last_updated_at=new_state.last_updated_at,
                    error_message=safe_error,
                )

            if self.db is not None:
                await self.db.upsert_latest_state(new_state, consecutive_failures=failures)

            return new_state, transition, failures

    async def mark_account_disabled(
        self,
        platform: Platform | str,
        account_key: str,
        *,
        handle: str | None = None,
        label: str | None = None,
        reason: str | None = None,
    ) -> AccountState:
        """Mark an account as DISABLED (e.g., when disabled in config or missing optional creds)."""
        from social_stats.collectors.base import sanitize_error_message

        safe_reason = sanitize_error_message(reason) if reason is not None else None
        p = Platform(str(platform).lower())
        key = (p, account_key)
        async with self._lock:
            prev = self._states.get(key)
            state = AccountState(
                platform=p,
                account_key=account_key,
                handle=handle if handle is not None else (prev.handle if prev else None),
                label=label if label is not None else (prev.label if prev else None),
                status=CollectorStatus.DISABLED,
                last_updated_at=prev.last_updated_at if prev else None,
                last_attempt_at=prev.last_attempt_at if prev else None,
                error_message=safe_reason,
                metrics=prev.metrics if prev else AccountMetrics(),
            )
            self._states[key] = state
            self._failures[key] = 0
            return state
