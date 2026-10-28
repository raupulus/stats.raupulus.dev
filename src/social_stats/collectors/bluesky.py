"""Bluesky AT Protocol public collector (batch profiles + author feed)."""

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

BLUESKY_BASE_URL = "https://public.api.bsky.app/xrpc"
BLUESKY_GET_PROFILES_URL = f"{BLUESKY_BASE_URL}/app.bsky.actor.getProfiles"
BLUESKY_GET_AUTHOR_FEED_URL = f"{BLUESKY_BASE_URL}/app.bsky.feed.getAuthorFeed"
BLUESKY_MAX_BATCH_SIZE = 25


def _build_bsky_post_url(handle: str, uri: str | None) -> str | None:
    """Convert at://did:plc:.../app.bsky.feed.post/<rkey> into https://bsky.app/profile/.../post/<rkey>."""
    if not uri or "/app.bsky.feed.post/" not in uri:
        return None
    rkey = uri.rsplit("/app.bsky.feed.post/", 1)[-1]
    if not rkey:
        return None
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string into a timezone-aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class BlueskyCollector(BaseCollector):
    """Collects Bluesky follower counts, post counts, and latest original post interactions."""

    platform = Platform.BLUESKY
    default_poll_interval = 120

    async def _fetch_latest_post(
        self, client: httpx.AsyncClient, actor_handle: str
    ) -> LatestPostMetrics | None:
        """Fetch the most recent original post (excluding replies and reposts) for an actor."""
        resp = await client.get(
            BLUESKY_GET_AUTHOR_FEED_URL,
            params={
                "actor": actor_handle,
                "limit": 5,
                "filter": "posts_no_replies",
            },
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Bluesky getAuthorFeed failed for '{actor_handle}' with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        feed_items: list[dict[str, Any]] = payload.get("feed") or []

        for item in feed_items:
            # Skip reposts (where 'reason' is populated, e.g. reasonRepost)
            if item.get("reason") is not None:
                continue
            post: dict[str, Any] = item.get("post") or {}
            uri = post.get("uri")
            if not uri:
                continue

            record: dict[str, Any] = post.get("record") or {}
            created_at = _parse_iso_datetime(
                record.get("createdAt") or post.get("indexedAt")
            )
            likes = post.get("likeCount")
            comments = post.get("replyCount")
            reposts = post.get("repostCount") or 0
            quotes = post.get("quoteCount") or 0
            shares = (
                int(reposts) + int(quotes)
                if (post.get("repostCount") is not None or post.get("quoteCount") is not None)
                else None
            )

            author_handle = (post.get("author") or {}).get("handle") or actor_handle
            return LatestPostMetrics(
                post_id=str(uri),
                url=_build_bsky_post_url(str(author_handle), str(uri)),
                published_at=created_at,
                views=None,
                likes=int(likes) if likes is not None else None,
                comments=int(comments) if comments is not None else None,
                shares=shares,
            )

        return None

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        handle_to_acc: dict[str, AccountConfig] = {}
        for acc in accounts:
            actor = (acc.handle or acc.account_key).lstrip("@").lower()
            handle_to_acc[actor] = acc

        actors_list = list(handle_to_acc.keys())
        profile_data_by_handle: dict[str, dict[str, Any]] = {}

        for idx in range(0, len(actors_list), BLUESKY_MAX_BATCH_SIZE):
            chunk = actors_list[idx : idx + BLUESKY_MAX_BATCH_SIZE]
            resp = await client.get(
                BLUESKY_GET_PROFILES_URL,
                params=[("actors", actor) for actor in chunk],
            )
            if resp.status_code != 200:
                raise CollectorError(
                    f"Bluesky getProfiles failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            payload: dict[str, Any] = resp.json()
            for prof in payload.get("profiles") or []:
                h = str(prof.get("handle", "")).lower()
                if h:
                    profile_data_by_handle[h] = prof

        results: dict[str, AccountMetrics] = {}
        for actor, acc in handle_to_acc.items():
            prof = profile_data_by_handle.get(actor)
            if prof is None:
                self.record_account_error(
                    acc.account_key,
                    f"Bluesky profile '{actor}' not found in getProfiles response",
                )
                continue

            followers = prof.get("followersCount")
            posts = prof.get("postsCount")

            latest_post: LatestPostMetrics | None = None
            try:
                latest_post = await self._fetch_latest_post(client, actor)
            except Exception as exc:
                # If feed fails, record error for account so stale handling applies
                self.record_account_error(acc.account_key, str(exc))
                continue

            base_metrics = AccountMetrics(
                followers_total=int(followers) if followers is not None else None,
                posts_total=int(posts) if posts is not None else None,
                views_total=None,
                latest_post=latest_post,
            )
            enriched = await self.enrich_with_snapshots(acc.account_key, base_metrics)
            results[acc.account_key] = enriched

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect metrics for all active Bluesky accounts."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
