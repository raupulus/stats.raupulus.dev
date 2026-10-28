"""LinkedIn isolated Level 3 collector supporting organization API and personal Voyager modes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_USER_AGENT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics, LatestPostMetrics
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository

LINKEDIN_ORG_FOLLOWERS_URL = (
    "https://api.linkedin.com/rest/organizationalEntityFollowerStatistics"
)
LINKEDIN_ORG_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_VOYAGER_PROFILE_URL = (
    "https://www.linkedin.com/voyager/api/identity/dash/profiles"
)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class LinkedInCollector(BaseCollector):
    """
    Isolated LinkedIn collector.
    If credentials are not provided for an account, marks it DISABLED without error alerts.
    """

    platform = Platform.LINKEDIN
    default_poll_interval = 3600

    def __init__(
        self,
        *,
        access_token: str = "",
        li_at_cookie: str = "",
        db: Database | None = None,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.access_token = access_token.strip()
        self.li_at_cookie = li_at_cookie.strip()
        self.db = db

    async def _resolve_org_token(self, credentials_ref: str) -> str:
        if self.db is not None:
            stored = await self.db.get_auth_token("linkedin", credentials_ref)
            if stored is not None and stored.access_token:
                return stored.access_token
        return self.access_token

    async def _collect_organization(
        self,
        client: httpx.AsyncClient,
        handle: str,
        token: str,
    ) -> AccountMetrics:
        org_urn = (
            handle
            if handle.startswith("urn:li:organization:")
            else f"urn:li:organization:{handle}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": "202405",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        f_resp = await client.get(
            LINKEDIN_ORG_FOLLOWERS_URL,
            params={"q": "organizationalEntity", "organizationalEntity": org_urn},
            headers=headers,
        )
        if f_resp.status_code != 200:
            raise CollectorError(
                f"LinkedIn organization followers failed with HTTP {f_resp.status_code}",
                status_code=f_resp.status_code,
            )

        f_data: dict[str, Any] = f_resp.json()
        elements: list[dict[str, Any]] = f_data.get("elements") or []
        followers_total: int | None = None
        if elements:
            follower_counts = elements[0].get("followerCounts") or {}
            organic = _parse_int(follower_counts.get("organicFollowerCount")) or 0
            paid = _parse_int(follower_counts.get("paidFollowerCount")) or 0
            followers_total = organic + paid

        p_resp = await client.get(
            LINKEDIN_ORG_POSTS_URL,
            params={"q": "author", "author": org_urn, "count": 1},
            headers=headers,
        )
        posts_total: int | None = None
        latest_post: LatestPostMetrics | None = None
        if p_resp.status_code == 200:
            p_data: dict[str, Any] = p_resp.json()
            paging = p_data.get("paging") or {}
            posts_total = _parse_int(paging.get("total"))
            p_elements: list[dict[str, Any]] = p_data.get("elements") or []
            if p_elements:
                post = p_elements[0]
                post_urn = str(post.get("id") or "")
                published_ms = _parse_int(post.get("publishedAt"))
                stats = post.get("socialDetail") or {}
                latest_post = LatestPostMetrics(
                    post_id=post_urn or None,
                    url=(
                        f"https://www.linkedin.com/feed/update/{post_urn}/"
                        if post_urn
                        else None
                    ),
                    published_at=(
                        datetime.fromtimestamp(published_ms / 1000.0, tz=UTC)
                        if published_ms is not None
                        else None
                    ),
                    views=_parse_int(stats.get("impressionCount")),
                    likes=_parse_int(stats.get("likeCount")),
                    comments=_parse_int(stats.get("commentCount")),
                    shares=_parse_int(stats.get("shareCount")),
                )

        return AccountMetrics(
            followers_total=followers_total,
            posts_total=posts_total,
            views_total=None,
            latest_post=latest_post,
        )

    async def _collect_personal(
        self,
        client: httpx.AsyncClient,
        handle: str,
        li_at: str,
    ) -> AccountMetrics:
        headers = {
            "Cookie": f"li_at={li_at}; JSESSIONID=\"ajax:0000000000000000000\"",
            "csrf-token": "ajax:0000000000000000000",
            "User-Agent": DEFAULT_USER_AGENT,
            "x-restli-protocol-version": "2.0.0",
        }
        resp = await client.get(
            LINKEDIN_VOYAGER_PROFILE_URL,
            params={"q": "memberIdentity", "memberIdentity": handle},
            headers=headers,
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"LinkedIn Voyager profile request failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        payload: dict[str, Any] = resp.json()
        elements: list[dict[str, Any]] = payload.get("elements") or []
        if not elements:
            raise CollectorError(
                f"LinkedIn Voyager returned empty elements for '{handle}'"
            )

        prof = elements[0]
        followers = _parse_int(
            prof.get("followerCount")
            or (prof.get("followingInfo") or {}).get("followerCount")
        )
        posts = _parse_int(prof.get("activityCount"))

        latest_post: LatestPostMetrics | None = None
        latest_act = prof.get("latestActivity")
        if isinstance(latest_act, dict) and latest_act.get("id"):
            act_id = str(latest_act["id"])
            latest_post = LatestPostMetrics(
                post_id=act_id,
                url=f"https://www.linkedin.com/feed/update/{act_id}/",
                views=_parse_int(latest_act.get("views")),
                likes=_parse_int(latest_act.get("likes")),
                comments=_parse_int(latest_act.get("comments")),
                shares=_parse_int(latest_act.get("shares")),
            )

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
            latest_post=latest_post,
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}

        for acc in accounts:
            handle = (acc.handle or acc.account_key).lstrip("@").lower()
            if acc.account_type == "organization":
                token = await self._resolve_org_token(acc.credentials_ref)
                if not token:
                    self.record_account_disabled(
                        acc.account_key,
                        "LINKEDIN_ACCESS_TOKEN not configured for organization account",
                    )
                    continue
                try:
                    metrics = await self._collect_organization(client, handle, token)
                    results[acc.account_key] = await self.enrich_with_snapshots(
                        acc.account_key, metrics
                    )
                except Exception as exc:
                    self.record_account_error(
                        acc.account_key, f"{type(exc).__name__}: {exc}"
                    )
            else:
                if not self.li_at_cookie:
                    self.record_account_disabled(
                        acc.account_key,
                        "LINKEDIN_LI_AT_COOKIE not configured for personal account",
                    )
                    continue
                try:
                    metrics = await self._collect_personal(
                        client, handle, self.li_at_cookie
                    )
                    results[acc.account_key] = await self.enrich_with_snapshots(
                        acc.account_key, metrics
                    )
                except Exception as exc:
                    self.record_account_error(
                        acc.account_key, f"{type(exc).__name__}: {exc}"
                    )

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect LinkedIn metrics or mark accounts DISABLED when unconfigured."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
