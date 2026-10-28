"""Keycounter collector (keystrokes and mouse clicks) via api.raupulus.dev API v2."""

from __future__ import annotations

from typing import Any

import httpx

from social_stats.collectors.base import DEFAULT_HTTP_TIMEOUT, BaseCollector
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

DEFAULT_KEYCOUNTER_API_URL = "https://api.raupulus.dev/api/v2/keycounter/stats"


def _parse_int(value: Any) -> int | None:
    """Safely convert a JSON numeric or string value to int."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class KeycounterCollector(BaseCollector):
    """
    Collects keyboard pulsations and mouse clicks (lifetime, today, last hour)
    from GET https://api.raupulus.dev/api/v2/keycounter/stats using Bearer token auth.
    """

    platform = Platform.KEYCOUNTER
    default_poll_interval = 60

    def __init__(
        self,
        *,
        api_token: str = "",
        api_url: str = DEFAULT_KEYCOUNTER_API_URL,
        settings: Settings | None = None,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.api_token = api_token.strip()
        self.api_url = api_url.strip() or DEFAULT_KEYCOUNTER_API_URL
        self.settings = settings

    def _resolve_token(self, acc: AccountConfig) -> str:
        """Resolve Bearer token for the given account's credentials_ref."""
        if self.settings is not None:
            resolved = self.settings.get_keycounter_token(acc.credentials_ref)
            if resolved:
                return resolved
        return self.api_token

    def _resolve_url(self, acc: AccountConfig) -> str:
        """Resolve API endpoint URL, allowing per-account override via instance if needed."""
        if acc.instance and acc.instance.strip().startswith(("http://", "https://")):
            return acc.instance.strip()
        if self.settings is not None and self.settings.keycounter_api_url.strip():
            return self.settings.keycounter_api_url.strip()
        return self.api_url

    async def _fetch_keycounter_stats(
        self,
        client: httpx.AsyncClient,
        url: str,
        token: str,
    ) -> tuple[AccountMetrics | None, str | None]:
        """Execute GET request against Keycounter API v2 and parse response."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        try:
            resp = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            return None, f"Keycounter HTTP transport error: {type(exc).__name__}: {exc}"

        payload: dict[str, Any] | None = None
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                payload = parsed
        except ValueError:
            payload = None

        if resp.status_code != 200:
            api_msg = (
                str(payload.get("message"))
                if payload and payload.get("message")
                else f"HTTP {resp.status_code}"
            )
            return None, f"Keycounter API error (HTTP {resp.status_code}): {api_msg}"

        if payload is None:
            return None, "Keycounter API returned non-JSON or invalid root payload"

        if payload.get("success") is False:
            api_msg = str(payload.get("message") or "Unknown API error")
            return None, f"Keycounter API reported success=false: {api_msg}"

        data = payload.get("data")
        if not isinstance(data, dict):
            return None, "Keycounter API payload missing 'data' object"

        pulsations_total = _parse_int(data.get("lifetime_pulsations"))
        pulsations_today = _parse_int(data.get("today_pulsations"))
        pulsations_last_1h = _parse_int(data.get("last_hour_pulsations"))
        clicks_total = _parse_int(data.get("lifetime_clicks"))
        clicks_today = _parse_int(data.get("today_clicks"))
        clicks_last_1h = _parse_int(data.get("last_hour_clicks"))

        if pulsations_total is None and clicks_total is None:
            return (
                None,
                "Keycounter API 'data' missing both 'lifetime_pulsations' and 'lifetime_clicks'",
            )

        metrics = AccountMetrics(
            pulsations_total=pulsations_total,
            pulsations_today=pulsations_today,
            pulsations_last_1h=pulsations_last_1h,
            clicks_total=clicks_total,
            clicks_today=clicks_today,
            clicks_last_1h=clicks_last_1h,
            window_1h_complete=pulsations_last_1h is not None or clicks_last_1h is not None,
            window_24h_complete=pulsations_today is not None or clicks_today is not None,
        )
        return metrics, None

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}
        request_cache: dict[tuple[str, str], tuple[AccountMetrics | None, str | None]] = {}

        for acc in accounts:
            token = self._resolve_token(acc)
            if not token:
                self.record_account_disabled(
                    acc.account_key,
                    f"Missing KEYCOUNTER_API_TOKEN for credentials_ref '{acc.credentials_ref}'",
                )
                continue

            url = self._resolve_url(acc)
            cache_key = (url, token)
            if cache_key not in request_cache:
                request_cache[cache_key] = await self._fetch_keycounter_stats(
                    client, url, token
                )

            metrics, err_msg = request_cache[cache_key]
            if metrics is None:
                self.record_account_error(
                    acc.account_key,
                    err_msg or "Keycounter collection failed",
                )
                continue

            account_metrics = metrics.model_copy(deep=True)
            if self.snapshot_repo is not None:
                await self.snapshot_repo.insert_snapshot(
                    self.platform,
                    acc.account_key,
                    account_metrics,
                    timestamp=self._cycle_now_ts,
                )
                self.enriched_accounts.add(acc.account_key)

            results[acc.account_key] = account_metrics

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect keycounter metrics for all configured accounts."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
