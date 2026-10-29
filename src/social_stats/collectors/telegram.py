"""Telegram public channel web-preview collector (zero tokens in URLs)."""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime

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
from social_stats.storage.snapshot_repo import SnapshotRepository

TELEGRAM_WEB_BASE = "https://t.me"

_COUNTER_BLOCK_RE = re.compile(
    r'<div class="tgme_channel_info_counter">\s*'
    r'<span class="counter_value">([^<]+)</span>\s*'
    r'<span class="counter_type">([^<]+)</span>',
    re.IGNORECASE,
)
_PAGE_EXTRA_SUBS_RE = re.compile(
    r'<div class="tgme_page_extra">\s*([0-9][0-9.,\sKkMmBb]*)\s*(?:subscribers?|members?)\b',
    re.IGNORECASE,
)
_DATA_POST_RE = re.compile(
    r'data-post="([^"/]+)/(\d+)"',
    re.IGNORECASE,
)
_MSG_VIEWS_RE = re.compile(
    r'<span class="tgme_widget_message_views">([^<]+)</span>',
    re.IGNORECASE,
)
_MSG_TIME_RE = re.compile(
    r'<time[^>]+datetime="([^"]+)"',
    re.IGNORECASE,
)


def _clean_telegram_handle(raw: str | None) -> str:
    val = (raw or "").strip()
    for prefix in ("https://t.me/s/", "http://t.me/s/", "https://t.me/", "http://t.me/", "t.me/s/", "t.me/"):
        if val.lower().startswith(prefix):
            val = val[len(prefix) :]
            break
    return val.strip().lstrip("@").strip("/")


def _parse_shorthand_int(raw: str | None) -> int | None:
    if not raw:
        return None
    cleaned = html_lib.unescape(raw).strip().replace("\xa0", "").replace(" ", "").upper()
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


class TelegramCollector(BaseCollector):
    """
    Collects public Telegram channel subscribers, message sequence count,
    and latest message views from https://t.me/s/{handle} without Bot tokens.
    """

    platform = Platform.TELEGRAM
    default_poll_interval = 300

    def __init__(
        self,
        *,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)

    def _extract_subscribers_from_html(self, html: str) -> int | None:
        for raw_val, raw_type in _COUNTER_BLOCK_RE.findall(html):
            ctype = raw_type.strip().lower()
            if "subscriber" in ctype or "member" in ctype:
                parsed = _parse_shorthand_int(raw_val)
                if parsed is not None:
                    return parsed

        extra_match = _PAGE_EXTRA_SUBS_RE.search(html)
        if extra_match:
            return _parse_shorthand_int(extra_match.group(1))
        return None

    def _extract_latest_message(self, html: str, handle: str) -> tuple[int | None, LatestPostMetrics | None]:
        matches = list(_DATA_POST_RE.finditer(html))
        if not matches:
            return None, None

        best_match: re.Match[str] | None = None
        max_post_id = -1
        for m in matches:
            post_channel = m.group(1)
            if post_channel.lower() != handle.lower():
                continue
            pid = int(m.group(2))
            if pid > max_post_id:
                max_post_id = pid
                best_match = m

        if best_match is None or max_post_id < 0:
            return None, None

        start_idx = best_match.start()
        next_msg_idx = html.find("tgme_widget_message_wrap", start_idx + 20)
        block = html[start_idx : next_msg_idx if next_msg_idx != -1 else start_idx + 12_000]

        views_match = _MSG_VIEWS_RE.search(block)
        time_match = _MSG_TIME_RE.search(block)

        latest = LatestPostMetrics(
            post_id=str(max_post_id),
            url=f"{TELEGRAM_WEB_BASE}/{handle}/{max_post_id}",
            published_at=_parse_iso_datetime(time_match.group(1)) if time_match else None,
            views=_parse_shorthand_int(views_match.group(1)) if views_match else None,
        )
        return max_post_id, latest

    async def _collect_single_account(
        self,
        client: httpx.AsyncClient,
        acc: AccountConfig,
    ) -> AccountMetrics:
        handle = _clean_telegram_handle(acc.handle or acc.account_key)
        if not handle:
            raise CollectorError("Telegram channel missing handle")

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        preview_resp = await client.get(
            f"{TELEGRAM_WEB_BASE}/s/{handle}",
            headers=headers,
            follow_redirects=True,
        )
        if preview_resp.status_code != 200:
            raise CollectorError(
                f"Telegram preview failed for '{handle}' with HTTP {preview_resp.status_code}",
                status_code=preview_resp.status_code,
            )

        html = preview_resp.text
        subscribers = self._extract_subscribers_from_html(html)
        max_post_id, latest_post = self._extract_latest_message(html, handle)

        if subscribers is None:
            landing_resp = await client.get(
                f"{TELEGRAM_WEB_BASE}/{handle}",
                headers=headers,
                follow_redirects=True,
            )
            if landing_resp.status_code == 200:
                subscribers = self._extract_subscribers_from_html(landing_resp.text)

        if subscribers is None and latest_post is None:
            raise CollectorError(
                f"Telegram channel '{handle}' not found or exposes no public metrics"
            )

        base_metrics = AccountMetrics(
            followers_total=subscribers,
            posts_total=max_post_id,
            views_total=latest_post.views if latest_post is not None else None,
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
                results[acc.account_key] = await self._collect_single_account(client, acc)
            except Exception as exc:
                self.record_account_error(acc.account_key, f"{type(exc).__name__}: {exc}")
        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect metrics across public Telegram channels, isolating failures per channel."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
