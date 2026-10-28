"""Abstract base class and shared HTTP/retry utilities for platform collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

DEFAULT_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class CollectorError(Exception):
    """Raised when a collector encounters an upstream HTTP or parsing failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseCollector(ABC):
    """Common interface for all social media and system metric collectors."""

    platform: Platform
    default_poll_interval: int = 300

    def __init__(
        self,
        *,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.snapshot_repo = snapshot_repo
        self._external_client = http_client
        self.last_errors: dict[str, str] = {}
        self.disabled_accounts: dict[str, str] = {}

    def reset_cycle_tracking(self) -> None:
        """Clear per-account error and disabled tracking at the start of a batch cycle."""
        self.last_errors.clear()
        self.disabled_accounts.clear()

    def record_account_error(self, account_key: str, error_message: str) -> None:
        """Record an error for a specific account without aborting the rest of the batch."""
        self.last_errors[account_key] = error_message

    def record_account_disabled(self, account_key: str, reason: str) -> None:
        """Mark a specific account as disabled due to missing optional credentials."""
        self.disabled_accounts[account_key] = reason

    async def enrich_with_snapshots(
        self,
        account_key: str,
        metrics: AccountMetrics,
        now_ts: int | None = None,
    ) -> AccountMetrics:
        """If snapshot_repo is attached, calculate 1h/24h deltas and persist snapshot."""
        if self.snapshot_repo is None:
            return metrics
        return await self.snapshot_repo.enrich_and_record(
            platform=self.platform,
            account_key=account_key,
            metrics=metrics,
            timestamp=now_ts,
        )

    @abstractmethod
    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """
        Collect metrics for the deduplicated list of active accounts on this platform.
        Returns a mapping {account_key: AccountMetrics}.
        """
