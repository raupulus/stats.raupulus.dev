"""Async scheduler for periodic metric collection, exponential backoff, and SQLite pruning."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from social_stats.collectors.base import BaseCollector, sanitize_error_message
from social_stats.config.profiles import AccountConfig, ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.models.api import CollectorStatusData, MetricUpdateData
from social_stats.models.enums import Platform
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore, StatusTransition

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 3600
JITTER_RATIO = 0.05
PRUNE_INTERVAL_SECONDS = 86400

UpdateCallback = Callable[[MetricUpdateData], Awaitable[None]]
StatusCallback = Callable[[CollectorStatusData], Awaitable[None]]


def calculate_backoff_delay(
    base_interval: int,
    consecutive_failures: int,
    *,
    apply_jitter: bool = True,
) -> float:
    """
    Calculate next polling delay in seconds:
    delay = min(base_interval * (2 ** consecutive_failures), 3600)
    with ±5% random jitter when apply_jitter=True.
    """
    exponent = max(0, min(consecutive_failures, 10))
    raw_delay = float(min(base_interval * (2**exponent), MAX_BACKOFF_SECONDS))
    if not apply_jitter:
        return raw_delay
    jitter = raw_delay * JITTER_RATIO * random.uniform(-1.0, 1.0)
    return max(1.0, raw_delay + jitter)


class CollectorScheduler:
    """Orchestrates periodic collection cycles per platform and daily DB pruning."""

    def __init__(
        self,
        *,
        settings: Settings,
        registry: ProfilesRegistry,
        collectors: dict[Platform, BaseCollector],
        snapshot_repo: SnapshotRepository,
        state_store: StateStore,
        aggregator: ProfileAggregator,
        on_metric_update: UpdateCallback | None = None,
        on_status_change: StatusCallback | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.collectors = collectors
        self.snapshot_repo = snapshot_repo
        self.state_store = state_store
        self.aggregator = aggregator
        self.on_metric_update = on_metric_update
        self.on_status_change = on_status_change
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()

    async def _emit_status_transition(self, transition: StatusTransition) -> None:
        """Notify subscribers in all affected profiles when collector status changes."""
        if self.on_status_change is None:
            return
        affected = self.aggregator.get_profiles_referencing_account(
            transition.platform, transition.account_key
        )
        for profile_id, _acc_cfg in affected:
            payload = CollectorStatusData(
                profile_id=profile_id,
                platform=transition.platform,
                account_key=transition.account_key,
                previous_status=transition.previous_status,
                current_status=transition.current_status,
                last_updated_at=transition.last_updated_at,
                error_message=transition.error_message,
            )
            await self.on_status_change(payload)

    async def run_collector_once(
        self,
        collector: BaseCollector,
        accounts: list[AccountConfig],
        *,
        now: datetime | None = None,
    ) -> int:
        """
        Execute a single collection cycle for a platform collector.
        Returns maximum consecutive failures among accounts in this batch (for backoff).
        """
        if not accounts:
            return 0

        ts = now if now is not None else datetime.now(UTC)
        now_epoch = int(ts.timestamp())
        platform = collector.platform
        collector.reset_cycle_tracking(now_ts=now_epoch)

        start_monotonic = time.monotonic()
        try:
            batch_results = await collector.collect_batch(accounts)
        except Exception as exc:
            latency_ms = int((time.monotonic() - start_monotonic) * 1000)
            error_msg = sanitize_error_message(f"{type(exc).__name__}: {exc}")
            logger.warning(
                "collector_batch_failed platform=%s accounts=%d latency_ms=%d error=%s",
                platform,
                len(accounts),
                latency_ms,
                error_msg,
            )
            max_failures = 0
            for acc in accounts:
                _state, transition, failures = await self.state_store.record_account_failure(
                    platform,
                    acc.account_key,
                    error_msg,
                    account_config=acc,
                    now=ts,
                )
                max_failures = max(max_failures, failures)
                if transition is not None:
                    await self._emit_status_transition(transition)
            return max_failures

        latency_ms = int((time.monotonic() - start_monotonic) * 1000)
        max_failures = 0

        for acc in accounts:
            key = acc.account_key
            if key in collector.disabled_accounts:
                await self.state_store.mark_account_disabled(
                    platform,
                    key,
                    handle=acc.handle,
                    label=acc.label,
                    reason=collector.disabled_accounts[key],
                )
                continue

            if key not in batch_results:
                err_msg = sanitize_error_message(
                    collector.last_errors.get(
                        key, f"Account '{key}' not returned by {platform} collector"
                    )
                )
                logger.warning(
                    "collector_account_failed platform=%s account=%s latency_ms=%d error=%s",
                    platform,
                    key,
                    latency_ms,
                    err_msg,
                )
                _state, transition, failures = await self.state_store.record_account_failure(
                    platform,
                    key,
                    err_msg,
                    account_config=acc,
                    now=ts,
                )
                max_failures = max(max_failures, failures)
                if transition is not None:
                    await self._emit_status_transition(transition)
                continue

            raw_metrics = batch_results[key]
            if key in collector.enriched_accounts:
                enriched_metrics = raw_metrics
            else:
                enriched_metrics = await self.snapshot_repo.enrich_and_record(
                    platform=platform,
                    account_key=key,
                    metrics=raw_metrics,
                    timestamp=now_epoch,
                )

            outcome = await self.state_store.update_account_success(
                platform=platform,
                account_key=key,
                metrics=enriched_metrics,
                handle=acc.handle,
                label=acc.label,
                now=ts,
            )
            logger.info(
                "collector_account_ok platform=%s account=%s latency_ms=%d followers=%s views=%s",
                platform,
                key,
                latency_ms,
                enriched_metrics.followers_total,
                enriched_metrics.views_total,
            )

            if outcome.status_transition is not None:
                await self._emit_status_transition(outcome.status_transition)

            if outcome.diff.has_changes and self.on_metric_update is not None:
                affected = self.aggregator.get_profiles_referencing_account(platform, key)
                for profile_id, profile_acc_cfg in affected:
                    if profile_id == "global" and platform == Platform.CRYPTO:
                        summary = self.aggregator.get_global_crypto_summary().model_copy(
                            update={"accounts": []}
                        )
                    else:
                        pstats = self.aggregator.get_profile_stats(
                            profile_id, platform_filter=platform, now=ts
                        )
                        if pstats is None or platform not in pstats.platforms:
                            continue
                        summary = pstats.platforms[platform].model_copy(
                            update={"accounts": []}
                        )
                    account_for_profile = outcome.state.model_copy(
                        update={
                            "handle": profile_acc_cfg.handle or outcome.state.handle,
                            "label": profile_acc_cfg.label or outcome.state.label,
                        }
                    )
                    update_data = MetricUpdateData(
                        profile_id=profile_id,
                        platform=platform,
                        account_key=key,
                        label=profile_acc_cfg.label or outcome.state.label,
                        is_new_latest_post=outcome.diff.is_new_latest_post,
                        changes=outcome.diff.changes,
                        account=account_for_profile,
                        platform_summary=summary,
                    )
                    await self.on_metric_update(update_data)

        return max_failures

    async def _platform_loop(
        self,
        collector: BaseCollector,
        accounts: list[AccountConfig],
    ) -> None:
        """
        Continuous polling loop for a platform supporting individual per-account
        interval_minutes with batching, jitter, and exponential backoff.
        """
        default_interval = self.settings.get_poll_interval(str(collector.platform))
        next_due: dict[str, float] = {acc.account_key: 0.0 for acc in accounts}

        while not self._stop_event.is_set():
            now_mono = time.monotonic()
            due_accounts = [
                acc
                for acc in accounts
                if next_due.get(acc.account_key, 0.0) <= now_mono + 0.5
            ]

            if due_accounts:
                await self.run_collector_once(collector, due_accounts)
                completed_mono = time.monotonic()
                for acc in due_accounts:
                    acc_base_interval = acc.get_poll_interval_seconds(default_interval)
                    acc_failures = self.state_store.get_consecutive_failures(
                        collector.platform, acc.account_key
                    )
                    delay = calculate_backoff_delay(
                        acc_base_interval,
                        acc_failures,
                        apply_jitter=True,
                    )
                    next_due[acc.account_key] = completed_mono + delay

            earliest_due = min(next_due.values()) if next_due else (time.monotonic() + default_interval)
            sleep_seconds = max(0.1, earliest_due - time.monotonic())
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
            except TimeoutError:
                continue

    async def _pruning_loop(self) -> None:
        """Daily maintenance task pruning old SQLite snapshots and optimizing indexes."""
        while not self._stop_event.is_set():
            try:
                deleted = await self.snapshot_repo.prune_old_snapshots(
                    retention_days=self.settings.snapshot_retention_days
                )
                logger.info(
                    "sqlite_pruning_completed retention_days=%d deleted_rows=%d",
                    self.settings.snapshot_retention_days,
                    deleted,
                )
            except Exception as exc:
                logger.error(
                    "sqlite_pruning_failed error=%s",
                    sanitize_error_message(f"{type(exc).__name__}: {exc}"),
                )

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=PRUNE_INTERVAL_SECONDS
                )
            except TimeoutError:
                continue

    def start(self) -> None:
        """Start background polling tasks for all configured platforms and DB pruning."""
        self._stop_event.clear()
        unique_by_platform = self.registry.get_unique_accounts_by_platform(only_enabled=True)

        for platform_str, accounts in unique_by_platform.items():
            platform = Platform(platform_str)
            collector = self.collectors.get(platform)
            if collector is None or not accounts:
                continue
            task = asyncio.create_task(
                self._platform_loop(collector, accounts),
                name=f"collector-{platform}",
            )
            self._tasks.append(task)

        prune_task = asyncio.create_task(
            self._pruning_loop(),
            name="sqlite-pruning",
        )
        self._tasks.append(prune_task)

    async def stop(self) -> None:
        """Signal all background tasks to stop and wait for clean cancellation."""
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
