"""Mastodon multi-instance public REST API v1 collector."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics, LatestPostMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class MastodonCollector(BaseCollector):
    """Collects Mastodon account metrics across one or more federated instances."""

    platform = Platform.MASTODON
    default_poll_interval = 180

    def __init__(
        self,
        *,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self._account_id_cache: dict[str, str] = {}

    async def _collect_single_account(
        self,
        client: httpx.AsyncClient,
        acc: AccountConfig,
    ) -> AccountMetrics:
        instance = (acc.instance or "").strip().lower()
        handle = (acc.handle or "").strip().lstrip("@")
        if not instance or not handle:
            raise CollectorError(
                f"Mastodon account '{acc.account_key}' missing instance or handle"
            )

        lookup_url = f"https://{instance}/api/v1/accounts/lookup"
        lookup_resp = await client.get(lookup_url, params={"acct": handle})
        if lookup_resp.status_code != 200:
            raise CollectorError(
                f"Mastodon lookup failed on {instance} for '{handle}' "
                f"with HTTP {lookup_resp.status_code}",
                status_code=lookup_resp.status_code,
            )

        acct_data: dict[str, Any] = lookup_resp.json()
        internal_id = str(acct_data.get("id", ""))
        if not internal_id:
            raise CollectorError(
                f"Mastodon lookup on {instance} for '{handle}' did not return an account id"
            )
        self._account_id_cache[acc.account_key] = internal_id

        followers_count = acct_data.get("followers_count")
        statuses_count = acct_data.get("statuses_count")

        statuses_url = f"https://{instance}/api/v1/accounts/{internal_id}/statuses"
        statuses_resp = await client.get(
            statuses_url,
            params={
                "limit": 1,
                "exclude_replies": "true",
                "exclude_reblogs": "true",
            },
        )
        if statuses_resp.status_code != 200:
            raise CollectorError(
                f"Mastodon statuses request failed on {instance} for '{handle}' "
                f"with HTTP {statuses_resp.status_code}",
                status_code=statuses_resp.status_code,
            )

        statuses_list: list[dict[str, Any]] = statuses_resp.json()
        latest_post: LatestPostMetrics | None = None
        if statuses_list:
            toot = statuses_list[0]
            toot_id = toot.get("id")
            favs = toot.get("favourites_count")
            replies = toot.get("replies_count")
            reblogs = toot.get("reblogs_count")
            latest_post = LatestPostMetrics(
                post_id=str(toot_id) if toot_id is not None else None,
                url=toot.get("url"),
                published_at=_parse_iso_datetime(toot.get("created_at")),
                views=None,
                likes=int(favs) if favs is not None else None,
                comments=int(replies) if replies is not None else None,
                shares=int(reblogs) if reblogs is not None else None,
            )

        base_metrics = AccountMetrics(
            followers_total=int(followers_count) if followers_count is not None else None,
            posts_total=int(statuses_count) if statuses_count is not None else None,
            views_total=None,
            latest_post=latest_post,
        )
        return await self.enrich_with_snapshots(acc.account_key, base_metrics)

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}
        for acc in accounts:
            try:
                metrics = await self._collect_single_account(client, acc)
                results[acc.account_key] = metrics
            except Exception as exc:
                self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")
        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect metrics across Mastodon instances, isolating failures per instance/account."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
