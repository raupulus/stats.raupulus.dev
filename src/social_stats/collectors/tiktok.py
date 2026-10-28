"""TikTok collector using SSR hydration (__UNIVERSAL_DATA_FOR_REHYDRATION__) and Display API auto-refresh."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from curl_cffi.requests import AsyncSession

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

TIKTOK_PROFILE_URL_TEMPLATE = "https://www.tiktok.com/@{handle}"
TIKTOK_OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_VIDEO_LIST_URL = (
    "https://open.tiktokapis.com/v2/video/list/"
    "?fields=id,create_time,view_count,like_count,comment_count,share_count"
)

REHYDRATION_SCRIPT_REGEX = re.compile(
    r'<script[^>]+id=["\']__UNIVERSAL_DATA_FOR_REHYDRATION__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class TikTokCollector(BaseCollector):
    """Collects TikTok follower/video counts via SSR rehydration and optional Display API v2."""

    platform = Platform.TIKTOK
    default_poll_interval = 900

    def __init__(
        self,
        *,
        client_key: str = "",
        client_secret: str = "",
        db: Database | None = None,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
        use_curl_cffi: bool = False,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.client_key = client_key.strip()
        self.client_secret = client_secret.strip()
        self.db = db
        self.use_curl_cffi = use_curl_cffi

    def _parse_ssr_html(self, handle: str, html_text: str) -> AccountMetrics:
        match = REHYDRATION_SCRIPT_REGEX.search(html_text)
        if not match:
            raise CollectorError(
                f"TikTok SSR script __UNIVERSAL_DATA_FOR_REHYDRATION__ not found for '@{handle}'"
            )

        try:
            data: dict[str, Any] = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise CollectorError(f"Malformed JSON in TikTok SSR script: {exc}") from exc

        scope: dict[str, Any] = data.get("__DEFAULT_SCOPE__") or {}
        user_detail: dict[str, Any] = scope.get("webapp.user-detail") or {}
        user_info: dict[str, Any] = user_detail.get("userInfo") or {}
        stats: dict[str, Any] = user_info.get("stats") or {}

        if not stats:
            raise CollectorError(
                f"TikTok userInfo.stats missing in SSR payload for '@{handle}'"
            )

        followers = _parse_int(stats.get("followerCount"))
        posts = _parse_int(stats.get("videoCount"))

        item_list: list[dict[str, Any]] = (
            user_detail.get("itemList") or user_info.get("itemList") or []
        )
        latest_post: LatestPostMetrics | None = None
        if item_list:
            vid = item_list[0]
            vid_id = str(vid.get("id") or "")
            vstats: dict[str, Any] = vid.get("stats") or {}
            create_ts = _parse_int(vid.get("createTime"))
            if vid_id:
                latest_post = LatestPostMetrics(
                    post_id=vid_id,
                    url=f"https://www.tiktok.com/@{handle}/video/{vid_id}",
                    published_at=(
                        datetime.fromtimestamp(create_ts, tz=UTC)
                        if create_ts is not None
                        else None
                    ),
                    views=_parse_int(vstats.get("playCount")),
                    likes=_parse_int(vstats.get("diggCount")),
                    comments=_parse_int(vstats.get("commentCount")),
                    shares=_parse_int(vstats.get("shareCount")),
                )

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
            latest_post=latest_post,
        )

    async def _fetch_ssr_metrics(
        self, handle: str, client: httpx.AsyncClient
    ) -> AccountMetrics:
        url = TIKTOK_PROFILE_URL_TEMPLATE.format(handle=handle)
        headers = {"User-Agent": DEFAULT_USER_AGENT}

        if self.use_curl_cffi and self._external_client is None:
            async with AsyncSession(impersonate="chrome124", timeout=15.0) as session:
                c_resp = await session.get(url, headers=headers)
                if c_resp.status_code != 200:
                    raise CollectorError(
                        f"TikTok profile page returned HTTP {c_resp.status_code}",
                        status_code=c_resp.status_code,
                    )
                return self._parse_ssr_html(handle, c_resp.text)

        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise CollectorError(
                f"TikTok profile page returned HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        return self._parse_ssr_html(handle, resp.text)

    async def _fetch_display_api_latest_post(
        self,
        client: httpx.AsyncClient,
        handle: str,
        credentials_ref: str,
    ) -> LatestPostMetrics | None:
        """If a stored OAuth token exists in SQLite, refresh if needed and query Display API v2."""
        if self.db is None:
            return None

        stored = await self.db.get_auth_token("tiktok", credentials_ref)
        if stored is None:
            return None

        now_ts = int(datetime.now(UTC).timestamp())
        access_token = stored.access_token

        if (
            stored.expires_at is not None
            and stored.expires_at <= now_ts
            and stored.refresh_token
            and self.client_key
            and self.client_secret
        ):
            refresh_resp = await client.post(
                TIKTOK_OAUTH_TOKEN_URL,
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": stored.refresh_token,
                },
            )
            if refresh_resp.status_code == 200:
                rdata: dict[str, Any] = refresh_resp.json()
                new_access = str(rdata.get("access_token") or "")
                new_refresh = str(rdata.get("refresh_token") or stored.refresh_token)
                expires_in = _parse_int(rdata.get("expires_in")) or 86400
                if new_access:
                    access_token = new_access
                    await self.db.upsert_auth_token(
                        provider="tiktok",
                        credentials_ref=credentials_ref,
                        access_token=new_access,
                        refresh_token=new_refresh,
                        expires_at=now_ts + expires_in,
                        now_ts=now_ts,
                    )

        v_resp = await client.post(
            TIKTOK_VIDEO_LIST_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"max_count": 1},
        )
        if v_resp.status_code != 200:
            return None

        v_payload: dict[str, Any] = v_resp.json()
        videos: list[dict[str, Any]] = (v_payload.get("data") or {}).get("videos") or []
        if not videos:
            return None

        v = videos[0]
        vid_id = str(v.get("id") or "")
        if not vid_id:
            return None
        create_ts = _parse_int(v.get("create_time"))
        return LatestPostMetrics(
            post_id=vid_id,
            url=f"https://www.tiktok.com/@{handle}/video/{vid_id}",
            published_at=(
                datetime.fromtimestamp(create_ts, tz=UTC)
                if create_ts is not None
                else None
            ),
            views=_parse_int(v.get("view_count")),
            likes=_parse_int(v.get("like_count")),
            comments=_parse_int(v.get("comment_count")),
            shares=_parse_int(v.get("share_count")),
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}

        for acc in accounts:
            handle = (acc.handle or acc.account_key).lstrip("@").lower()
            try:
                metrics = await self._fetch_ssr_metrics(handle, client)
                try:
                    api_post = await self._fetch_display_api_latest_post(
                        client, handle, acc.credentials_ref
                    )
                    if api_post is not None:
                        metrics = metrics.model_copy(update={"latest_post": api_post})
                except Exception:
                    pass

                enriched = await self.enrich_with_snapshots(acc.account_key, metrics)
                results[acc.account_key] = enriched
            except Exception as exc:
                self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect TikTok metrics for all active accounts."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
