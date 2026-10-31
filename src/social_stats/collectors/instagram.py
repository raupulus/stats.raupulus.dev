"""Instagram dual-tier collector (Meta Graph API System User Token + Web Profile fallback)."""

from __future__ import annotations

import html as html_lib
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
from social_stats.config.settings import Settings, get_settings
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics, LatestPostMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

IG_GRAPH_BASE_URL = "https://graph.facebook.com/v21.0"
IG_WEB_PROFILE_URL = "https://www.instagram.com/api/v1/users/web_profile_info/"
IG_PUBLIC_APP_ID = "936619743392459"
IG_OG_USER_AGENT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
_IG_META_DESC_PATTERNS = (
    re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+property="og:description"', re.IGNORECASE),
    re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+name="description"', re.IGNORECASE),
)
_IG_METRICS_RE = re.compile(
    r"([0-9.,KkMmBb]+)\s*(?:Followers|seguidores),\s*([0-9.,KkMmBb]+)\s*(?:Following|siguiendo),\s*([0-9.,KkMmBb]+)\s*(?:Posts|publicaciones)",
    re.IGNORECASE,
)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_shorthand_int(val: str | None) -> int | None:
    if not val:
        return None
    cleaned = val.strip().replace(" ", "").upper()
    multiplier = 1
    if cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("B"):
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 3 and len(parts) > 1:
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts[-1]) == 3 and len(parts) > 1:
            cleaned = cleaned.replace(".", "")

    try:
        return int(float(cleaned) * multiplier)
    except (ValueError, TypeError):
        return None


def _parse_iso_datetime(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


class InstagramCollector(BaseCollector):
    """Collects Instagram metrics via Meta Graph API (Level A) or Web Profile API (Level B)."""

    platform = Platform.INSTAGRAM
    default_poll_interval = 900

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
        use_curl_cffi: bool = False,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.settings = settings if settings is not None else get_settings()
        self.use_curl_cffi = use_curl_cffi

    async def _fetch_level_a_graph_api(
        self,
        client: httpx.AsyncClient,
        ig_user_id: str,
        access_token: str,
    ) -> AccountMetrics:
        """Query Meta Graph API v21.0 using permanent System User Token."""
        url = f"{IG_GRAPH_BASE_URL}/{ig_user_id}"
        fields = (
            "followers_count,media_count,"
            "media.limit(1){id,permalink,timestamp,media_type,like_count,comments_count,play_count}"
        )
        resp = await client.get(
            url,
            params={
                "fields": fields,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Instagram Graph API failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        data: dict[str, Any] = resp.json()
        followers = _parse_int(data.get("followers_count"))
        posts = _parse_int(data.get("media_count"))

        media_list: list[dict[str, Any]] = (data.get("media") or {}).get("data") or []
        latest_post: LatestPostMetrics | None = None
        if media_list:
            item = media_list[0]
            media_type = str(item.get("media_type", "")).upper()
            views_val = (
                _parse_int(item.get("play_count"))
                if media_type in {"VIDEO", "REELS"}
                else None
            )
            latest_post = LatestPostMetrics(
                post_id=str(item.get("id")) if item.get("id") else None,
                url=item.get("permalink"),
                published_at=_parse_iso_datetime(item.get("timestamp")),
                views=views_val,
                likes=_parse_int(item.get("like_count")),
                comments=_parse_int(item.get("comments_count")),
                shares=None,
            )

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
            latest_post=latest_post,
        )

    def _parse_web_profile_json(self, payload: dict[str, Any]) -> AccountMetrics:
        user: dict[str, Any] = (payload.get("data") or {}).get("user") or {}
        if not user:
            raise CollectorError("Instagram web_profile_info missing data.user")

        followers = _parse_int((user.get("edge_followed_by") or {}).get("count"))
        timeline_media: dict[str, Any] = user.get("edge_owner_to_timeline_media") or {}
        posts = _parse_int(timeline_media.get("count"))
        edges: list[dict[str, Any]] = timeline_media.get("edges") or []

        latest_post: LatestPostMetrics | None = None
        if edges:
            node: dict[str, Any] = edges[0].get("node") or {}
            shortcode = node.get("shortcode")
            taken_ts = _parse_int(node.get("taken_at_timestamp"))
            is_video = bool(node.get("is_video", False))
            views_val = _parse_int(node.get("video_view_count")) if is_video else None
            likes_val = _parse_int(
                (node.get("edge_liked_by") or node.get("edge_media_preview_like") or {}).get(
                    "count"
                )
            )
            comments_val = _parse_int(
                (node.get("edge_media_to_comment") or {}).get("count")
            )
            latest_post = LatestPostMetrics(
                post_id=str(node.get("id")) if node.get("id") else None,
                url=f"https://www.instagram.com/p/{shortcode}/" if shortcode else None,
                published_at=(
                    datetime.fromtimestamp(taken_ts, tz=UTC)
                    if taken_ts is not None
                    else None
                ),
                views=views_val,
                likes=likes_val,
                comments=comments_val,
                shares=None,
            )

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
            latest_post=latest_post,
        )

    async def _fetch_level_b_web_profile(
        self,
        handle: str,
        client: httpx.AsyncClient | None = None,
    ) -> AccountMetrics:
        """Query Instagram web_profile_info endpoint with Chrome TLS impersonation."""
        headers = {
            "x-ig-app-id": IG_PUBLIC_APP_ID,
            "Referer": f"https://www.instagram.com/{handle}/",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if client is not None:
            resp = await client.get(
                IG_WEB_PROFILE_URL,
                params={"username": handle},
                headers=headers,
            )
            if resp.status_code != 200:
                raise CollectorError(
                    f"Instagram web_profile_info failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            return self._parse_web_profile_json(resp.json())

        async with AsyncSession(impersonate="chrome124", timeout=15.0) as session:
            c_resp = await session.get(
                IG_WEB_PROFILE_URL,
                params={"username": handle},
                headers=headers,
            )
            if c_resp.status_code != 200:
                raise CollectorError(
                    f"Instagram web_profile_info failed with HTTP {c_resp.status_code}",
                    status_code=c_resp.status_code,
                )
            return self._parse_web_profile_json(c_resp.json())

    async def _fetch_level_b_html_profile(
        self,
        handle: str,
        client: httpx.AsyncClient | None = None,
    ) -> AccountMetrics:
        """Fallback to parsing Instagram public profile OpenGraph meta tags."""
        url = f"https://www.instagram.com/{handle}/"
        headers = {
            "User-Agent": IG_OG_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        }
        if client is not None:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise CollectorError(
                    f"Instagram profile page failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            html = resp.text
        else:
            async with AsyncSession(impersonate="chrome124", timeout=15.0) as session:
                c_resp = await session.get(url, headers=headers)
                if c_resp.status_code != 200:
                    raise CollectorError(
                        f"Instagram profile page failed with HTTP {c_resp.status_code}",
                        status_code=c_resp.status_code,
                    )
                html = c_resp.text

        descriptions: list[str] = []
        for pattern in _IG_META_DESC_PATTERNS:
            for m in pattern.finditer(html):
                descriptions.append(html_lib.unescape(m.group(1)))

        if not descriptions:
            raise CollectorError("Instagram profile page missing og:description")

        parsed_match: re.Match[str] | None = None
        for desc in descriptions:
            parsed_match = _IG_METRICS_RE.search(desc)
            if parsed_match is not None:
                break

        if parsed_match is None:
            raise CollectorError(
                f"Could not parse metrics from Instagram og:description: {descriptions[0][:60]}"
            )

        followers = _parse_shorthand_int(parsed_match.group(1))
        posts = _parse_shorthand_int(parsed_match.group(3))

        return AccountMetrics(
            followers_total=followers,
            posts_total=posts,
            views_total=None,
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
        *,
        use_httpx_for_level_b: bool,
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}
        web_profile_blocked = False

        for acc in accounts:
            handle = (acc.handle or acc.account_key).lstrip("@").lower()
            ig_user_id, access_token = self.settings.get_instagram_credentials(
                acc.credentials_ref
            )
            metrics: AccountMetrics | None = None

            if ig_user_id and access_token:
                try:
                    metrics = await self._fetch_level_a_graph_api(
                        client, ig_user_id, access_token
                    )
                except Exception:
                    # Fallback from Level A to Level B
                    metrics = None

            if metrics is None and not web_profile_blocked:
                try:
                    metrics = await self._fetch_level_b_web_profile(
                        handle,
                        client=client if use_httpx_for_level_b else None,
                    )
                except CollectorError as exc:
                    if exc.status_code in {401, 403, 429}:
                        web_profile_blocked = True
                    metrics = None
                except Exception:
                    metrics = None

            if metrics is None:
                try:
                    metrics = await self._fetch_level_b_html_profile(
                        handle,
                        client=client if use_httpx_for_level_b else None,
                    )
                except Exception as exc:
                    self.record_account_error(
                        acc.account_key, f"{type(exc).__name__}: {exc}"
                    )
                    continue

            enriched = await self.enrich_with_snapshots(acc.account_key, metrics)
            results[acc.account_key] = enriched

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect Instagram metrics for all active accounts."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(
                self._external_client, accounts, use_httpx_for_level_b=True
            )

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(
                client, accounts, use_httpx_for_level_b=not self.use_curl_cffi
            )
