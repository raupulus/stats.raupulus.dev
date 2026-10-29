"""Facebook Page dual-tier collector (Meta Graph API Bearer Token + OpenGraph HTML fallback)."""

from __future__ import annotations

import html as html_lib
import re
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
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

FB_GRAPH_BASE_URL = "https://graph.facebook.com/v21.0"
FB_WEB_BASE_URL = "https://www.facebook.com"

_META_DESC_PATTERNS = (
    re.compile(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+property="og:description"', re.IGNORECASE),
    re.compile(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', re.IGNORECASE),
    re.compile(r'<meta[^>]+content="([^"]+)"[^>]+name="description"', re.IGNORECASE),
)
_FOLLOWERS_RE = re.compile(
    r"([0-9][0-9.,\s\xa0]*(?:[KkMmBb]|\s*mil)?)\s*(?:followers|seguidores)\b",
    re.IGNORECASE,
)
_LIKES_RE = re.compile(
    r"([0-9][0-9.,\s\xa0]*(?:[KkMmBb]|\s*mil)?)\s*(?:likes|me\s+gusta)\b",
    re.IGNORECASE,
)


def _parse_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_shorthand_int(raw: str | None) -> int | None:
    if not raw:
        return None
    cleaned = html_lib.unescape(raw).strip().replace("\xa0", " ").upper()
    multiplier = 1
    if cleaned.endswith("MIL"):
        multiplier = 1_000
        cleaned = cleaned[:-3].strip()
    else:
        cleaned = cleaned.replace(" ", "")
        if cleaned.endswith("K"):
            multiplier = 1_000
            cleaned = cleaned[:-1]
        elif cleaned.endswith("M"):
            multiplier = 1_000_000
            cleaned = cleaned[:-1]
        elif cleaned.endswith("B"):
            multiplier = 1_000_000_000
            cleaned = cleaned[:-1]

    cleaned = cleaned.replace(" ", "")
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


class FacebookCollector(BaseCollector):
    """
    Collects Facebook Page followers and likes (fan_count -> stars_total).
    Level A: Meta Graph API v21.0 using permanent System User Page Token in Bearer header.
    Level B: Public page OpenGraph HTML parsing via curl_cffi (Chrome TLS impersonation).
    """

    platform = Platform.FACEBOOK
    default_poll_interval = 1800

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
        page_id: str,
        access_token: str,
    ) -> AccountMetrics:
        resp = await client.get(
            f"{FB_GRAPH_BASE_URL}/{page_id}",
            params={"fields": "id,name,followers_count,fan_count"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise CollectorError(
                f"Facebook Graph API failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
            )

        data: dict[str, Any] = resp.json()
        followers = _parse_int(data.get("followers_count"))
        likes = _parse_int(data.get("fan_count"))
        if followers is None and likes is not None:
            followers = likes

        return AccountMetrics(
            followers_total=followers,
            stars_total=likes,
        )

    def _parse_public_html(self, html: str) -> AccountMetrics:
        descriptions: list[str] = []
        for pattern in _META_DESC_PATTERNS:
            for match in pattern.finditer(html):
                descriptions.append(html_lib.unescape(match.group(1)))

        if not descriptions:
            raise CollectorError("Facebook public page missing OpenGraph description meta tags")

        followers: int | None = None
        likes: int | None = None
        for desc in descriptions:
            if followers is None:
                m_fol = _FOLLOWERS_RE.search(desc)
                if m_fol:
                    followers = _parse_shorthand_int(m_fol.group(1))
            if likes is None:
                m_likes = _LIKES_RE.search(desc)
                if m_likes:
                    likes = _parse_shorthand_int(m_likes.group(1))
            if followers is not None and likes is not None:
                break

        if followers is None and likes is not None:
            followers = likes

        if followers is None and likes is None:
            raise CollectorError(
                "Could not parse followers or likes from Facebook public page metadata"
            )

        return AccountMetrics(
            followers_total=followers,
            stars_total=likes,
        )

    async def _fetch_level_b_html_page(
        self,
        handle: str,
        client: httpx.AsyncClient | None = None,
    ) -> AccountMetrics:
        url = f"{FB_WEB_BASE_URL}/{handle}/"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        }
        if client is not None:
            resp = await client.get(url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                raise CollectorError(
                    f"Facebook public page failed with HTTP {resp.status_code}",
                    status_code=resp.status_code,
                )
            html = resp.text
        else:
            async with AsyncSession(impersonate="chrome124", timeout=15.0) as session:
                c_resp = await session.get(url, headers=headers, allow_redirects=True)
                if c_resp.status_code != 200:
                    raise CollectorError(
                        f"Facebook public page failed with HTTP {c_resp.status_code}",
                        status_code=c_resp.status_code,
                    )
                html = c_resp.text

        return self._parse_public_html(html)

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
        *,
        use_httpx_for_level_b: bool,
    ) -> dict[str, AccountMetrics]:
        results: dict[str, AccountMetrics] = {}

        for acc in accounts:
            handle = (acc.handle or acc.id or acc.account_key or "").strip().lstrip("@").strip("/")
            cfg_page_id, access_token = self.settings.get_facebook_credentials(acc.credentials_ref)
            page_id = cfg_page_id or (acc.id or "").strip()

            metrics: AccountMetrics | None = None
            if page_id and access_token:
                try:
                    metrics = await self._fetch_level_a_graph_api(client, page_id, access_token)
                except Exception:
                    metrics = None

            if metrics is None:
                if not handle:
                    self.record_account_error(acc.account_key, "Facebook account missing handle")
                    continue
                try:
                    metrics = await self._fetch_level_b_html_page(
                        handle,
                        client=client if use_httpx_for_level_b else None,
                    )
                except Exception as exc:
                    self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")
                    continue

            results[acc.account_key] = await self.enrich_with_snapshots(acc.account_key, metrics)

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect Facebook Page metrics for all configured accounts."""
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
