"""Abstract base class and shared HTTP/retry utilities for platform collectors."""

from __future__ import annotations

import re
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

_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-~+/]+=*")
_SECRET_KV_PATTERN = re.compile(
    r"(?i)\b(key|api_key|access_token|refresh_token|client_secret|token|li_at|auth_token|ct0)"
    r"(\s*[=:]\s*)([^\s&\"',;]+)"
)
MAX_SANITIZED_ERROR_LENGTH = 240


def sanitize_error_message(message: str | None, *, max_length: int = MAX_SANITIZED_ERROR_LENGTH) -> str:
    """
    Redact full URLs, query parameters, Bearer tokens, and secret key-value pairs
    from collector/transport error messages before logging, caching, or persisting.
    """
    if not message:
        return ""
    cleaned = _URL_PATTERN.sub("[REDACTED_URL]", str(message))
    cleaned = _BEARER_PATTERN.sub("Bearer [REDACTED]", cleaned)
    cleaned = _SECRET_KV_PATTERN.sub(r"\1\2[REDACTED]", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_length:
        return f"{cleaned[: max_length - 3]}..."
    return cleaned


class CollectorError(Exception):
    """Raised when a collector encounters an upstream HTTP or parsing failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        sanitized = sanitize_error_message(message)
        super().__init__(sanitized)
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
        self.enriched_accounts: set[str] = set()
        self._cycle_now_ts: int | None = None

    def reset_cycle_tracking(self, *, now_ts: int | None = None) -> None:
        """Clear per-account error/disabled/enriched tracking at the start of a batch cycle."""
        self.last_errors.clear()
        self.disabled_accounts.clear()
        self.enriched_accounts.clear()
        self._cycle_now_ts = now_ts

    def record_account_error(self, account_key: str, error_message: str) -> None:
        """Record a sanitized error for a specific account without aborting the batch."""
        self.last_errors[account_key] = sanitize_error_message(error_message)

    def record_account_disabled(self, account_key: str, reason: str) -> None:
        """Mark a specific account as disabled due to missing optional credentials."""
        self.disabled_accounts[account_key] = sanitize_error_message(reason)

    async def enrich_with_snapshots(
        self,
        account_key: str,
        metrics: AccountMetrics,
        now_ts: int | None = None,
    ) -> AccountMetrics:
        """If snapshot_repo is attached, calculate 1h/24h deltas and persist snapshot."""
        if self.snapshot_repo is None:
            return metrics
        effective_ts = now_ts if now_ts is not None else self._cycle_now_ts
        enriched = await self.snapshot_repo.enrich_and_record(
            platform=self.platform,
            account_key=account_key,
            metrics=metrics,
            timestamp=effective_ts,
        )
        self.enriched_accounts.add(account_key)
        return enriched

    @abstractmethod
    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """
        Collect metrics for the deduplicated list of active accounts on this platform.
        Returns a mapping {account_key: AccountMetrics}.
        """
