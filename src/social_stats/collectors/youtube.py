"""YouTube Data API v3 batch collector supporting multichannel and handle resolution."""

from __future__ import annotations

from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_MAX_BATCH_SIZE = 50


def _parse_optional_int(val: Any) -> int | None:
    """Safely convert a string/int metric from Google API to int or None."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class YouTubeCollector(BaseCollector):
    """Collects YouTube channel statistics in batches of up to 50 channels per request."""

    platform = Platform.YOUTUBE
    default_poll_interval = 300

    def __init__(
        self,
        api_key: str,
        *,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.api_key = api_key.strip()
        self._handle_to_channel_id: dict[str, str] = {}

    async def _resolve_handle(
        self, client: httpx.AsyncClient, handle: str
    ) -> str | None:
        """Resolve a YouTube @handle to its canonical UC... channel_id."""
        clean_handle = handle.strip()
        if not clean_handle.startswith("@"):
            clean_handle = f"@{clean_handle}"

        resp = await client.get(
            YOUTUBE_CHANNELS_URL,
            params={
                "part": "id",
                "forHandle": clean_handle,
                "key": self.api_key,
            },
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"YouTube handle resolution failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        items = payload.get("items") or []
        if not items or "id" not in items[0]:
            return None
        return str(items[0]["id"])

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        if not self.api_key:
            raise CollectorError("YOUTUBE_API_KEY is not configured")

        # Map canonical channel_id -> list of account_keys requesting it
        channel_to_keys: dict[str, list[str]] = {}

        for acc in accounts:
            if acc.id:
                cid = acc.id.strip()
                channel_to_keys.setdefault(cid, []).append(acc.account_key)
                continue

            cached_cid = self._handle_to_channel_id.get(acc.account_key)
            if cached_cid is None and acc.handle:
                try:
                    cached_cid = await self._resolve_handle(client, acc.handle)
                except Exception as exc:
                    self.record_account_error(acc.account_key, str(exc))
                    continue

                if cached_cid is None:
                    self.record_account_error(
                        acc.account_key,
                        f"YouTube handle '{acc.handle}' not found",
                    )
                    continue
                self._handle_to_channel_id[acc.account_key] = cached_cid

            if cached_cid:
                channel_to_keys.setdefault(cached_cid, []).append(acc.account_key)

        all_channel_ids = list(channel_to_keys.keys())
        results: dict[str, AccountMetrics] = {}

        for idx in range(0, len(all_channel_ids), YOUTUBE_MAX_BATCH_SIZE):
            chunk_ids = all_channel_ids[idx : idx + YOUTUBE_MAX_BATCH_SIZE]
            resp = await client.get(
                YOUTUBE_CHANNELS_URL,
                params={
                    "part": "statistics,snippet",
                    "id": ",".join(chunk_ids),
                    "key": self.api_key,
                },
            )
            if resp.status_code != 200:
                raise CollectorError(
                    f"YouTube channels batch request failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )

            payload: dict[str, Any] = resp.json()
            items = payload.get("items") or []
            found_cids: set[str] = set()

            for item in items:
                cid = str(item.get("id", ""))
                if not cid or cid not in channel_to_keys:
                    continue
                found_cids.add(cid)
                stats: dict[str, Any] = item.get("statistics") or {}

                hidden_subs = bool(stats.get("hiddenSubscriberCount", False))
                followers_total = (
                    None
                    if hidden_subs
                    else _parse_optional_int(stats.get("subscriberCount"))
                )
                posts_total = _parse_optional_int(stats.get("videoCount"))
                views_total = _parse_optional_int(stats.get("viewCount"))

                base_metrics = AccountMetrics(
                    followers_total=followers_total,
                    posts_total=posts_total,
                    views_total=views_total,
                    latest_post=None,
                )

                for account_key in channel_to_keys[cid]:
                    enriched = await self.enrich_with_snapshots(
                        account_key, base_metrics
                    )
                    results[account_key] = enriched

            for requested_cid in chunk_ids:
                if requested_cid not in found_cids:
                    for account_key in channel_to_keys[requested_cid]:
                        self.record_account_error(
                            account_key,
                            f"YouTube channel '{requested_cid}' not returned by API",
                        )

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect metrics for all active YouTube channels in chunks of up to 50 IDs."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
