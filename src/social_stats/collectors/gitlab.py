"""GitLab multi-instance REST API v4 + public XHR followers collector."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_USER_AGENT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics, LatestPostMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository

MAX_GITLAB_PAGES = 20
_GL_CARD_RE = re.compile(r'class="[^"]*\bgl-card\b', re.IGNORECASE)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_instance(raw_instance: str | None) -> str:
    cleaned = (raw_instance or "gitlab.com").strip().lower()
    cleaned = cleaned.removeprefix("https://").removeprefix("http://").rstrip("/")
    return cleaned or "gitlab.com"


class GitLabCollector(BaseCollector):
    """
    Collects GitLab user metrics across gitlab.com or self-hosted instances:
    - followers_total via REST API v4 (/api/v4/users/:id) when permitted or authenticated,
      with automatic fallback to public XHR JSON (/users/:handle/followers.json).
    - posts_total (public projects), stars_total (star_count sum), and forks_total
      via paginated /api/v4/users/:id/projects.
    """

    platform = Platform.GITLAB
    default_poll_interval = 900

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        snapshot_repo: SnapshotRepository | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(snapshot_repo=snapshot_repo, http_client=http_client)
        self.settings = settings
        self._user_id_cache: dict[str, str] = {}

    def _build_api_headers(self, credentials_ref: str | None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.settings is not None:
            token = self.settings.get_gitlab_token(credentials_ref or "MAIN")
            if token:
                headers["PRIVATE-TOKEN"] = token
        return headers

    async def _resolve_user_id(
        self,
        client: httpx.AsyncClient,
        instance: str,
        handle: str,
        acc: AccountConfig,
        headers: dict[str, str],
    ) -> str:
        if acc.id and acc.id.strip():
            uid = acc.id.strip()
            self._user_id_cache[acc.account_key] = uid
            return uid

        lookup_resp = await client.get(
            f"https://{instance}/api/v4/users",
            params={"username": handle},
            headers=headers,
        )
        if lookup_resp.status_code != 200:
            raise CollectorError(
                f"GitLab user lookup failed on {instance} for '{handle}' "
                f"with HTTP {lookup_resp.status_code}",
                status_code=lookup_resp.status_code,
            )

        users_list: list[dict[str, Any]] = lookup_resp.json()
        if not users_list:
            raise CollectorError(f"GitLab user '{handle}' not found on {instance}", status_code=404)

        uid = str(users_list[0].get("id") or self._user_id_cache.get(acc.account_key, ""))
        if not uid:
            raise CollectorError(f"GitLab lookup on {instance} for '{handle}' missing numeric id")
        self._user_id_cache[acc.account_key] = uid
        return uid

    async def _fetch_followers_xhr_fallback(
        self,
        client: httpx.AsyncClient,
        instance: str,
        handle: str,
    ) -> int | None:
        xhr_headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        total_followers = 0
        for page in range(1, MAX_GITLAB_PAGES + 1):
            resp = await client.get(
                f"https://{instance}/users/{handle}/followers.json",
                params={"page": page},
                headers=xhr_headers,
            )
            if resp.status_code != 200:
                if page == 1:
                    return None
                break

            payload: dict[str, Any] = resp.json()
            explicit_count = payload.get("count")
            if isinstance(explicit_count, int):
                return explicit_count

            html_fragment = str(payload.get("html") or "")
            cards_on_page = len(_GL_CARD_RE.findall(html_fragment))
            total_followers += cards_on_page

            if cards_on_page == 0:
                break
            next_marker = f"page={page + 1}"
            if next_marker not in html_fragment and 'rel="next"' not in html_fragment:
                break

        return total_followers

    async def _fetch_followers_count(
        self,
        client: httpx.AsyncClient,
        instance: str,
        uid: str,
        handle: str,
        headers: dict[str, str],
    ) -> int | None:
        detail_resp = await client.get(
            f"https://{instance}/api/v4/users/{uid}",
            headers=headers,
        )
        if detail_resp.status_code == 200:
            detail_data: dict[str, Any] = detail_resp.json()
            followers_val = detail_data.get("followers")
            if isinstance(followers_val, int):
                return followers_val

        return await self._fetch_followers_xhr_fallback(client, instance, handle)

    async def _collect_single_account(
        self,
        client: httpx.AsyncClient,
        acc: AccountConfig,
    ) -> AccountMetrics:
        instance = _normalize_instance(acc.instance)
        handle = (acc.handle or "").strip().lstrip("@")
        if not handle:
            raise CollectorError(f"GitLab account '{acc.account_key}' missing handle")

        headers = self._build_api_headers(acc.credentials_ref)
        uid = await self._resolve_user_id(client, instance, handle, acc, headers)
        followers_total = await self._fetch_followers_count(client, instance, uid, handle, headers)

        stars_sum = 0
        forks_sum = 0
        counted_projects = 0
        x_total_projects: int | None = None
        latest_post: LatestPostMetrics | None = None

        for page in range(1, MAX_GITLAB_PAGES + 1):
            proj_resp = await client.get(
                f"https://{instance}/api/v4/users/{uid}/projects",
                params={
                    "per_page": 100,
                    "page": page,
                    "order_by": "last_activity_at",
                    "sort": "desc",
                },
                headers=headers,
            )
            if proj_resp.status_code != 200:
                raise CollectorError(
                    f"GitLab projects listing failed on {instance} for '{handle}' "
                    f"with HTTP {proj_resp.status_code}",
                    status_code=proj_resp.status_code,
                )

            if page == 1:
                raw_x_total = (proj_resp.headers.get("x-total") or "").strip()
                if raw_x_total.isdigit():
                    x_total_projects = int(raw_x_total)

            projects_page: list[dict[str, Any]] = proj_resp.json()
            if not projects_page:
                break

            if page == 1:
                top = projects_page[0]
                proj_id = top.get("id")
                latest_post = LatestPostMetrics(
                    post_id=str(proj_id) if proj_id is not None else top.get("path"),
                    url=top.get("web_url"),
                    published_at=_parse_iso_datetime(
                        top.get("last_activity_at") or top.get("created_at")
                    ),
                    views=None,
                    likes=int(top.get("star_count") or 0),
                    comments=int(top.get("open_issues_count") or 0),
                    shares=int(top.get("forks_count") or 0),
                )

            for proj in projects_page:
                stars_sum += int(proj.get("star_count") or 0)
                forks_sum += int(proj.get("forks_count") or 0)
            counted_projects += len(projects_page)

            if "x-next-page" in proj_resp.headers:
                if not proj_resp.headers["x-next-page"].strip():
                    break
            elif len(projects_page) < 100:
                break

        posts_total = x_total_projects if x_total_projects is not None else counted_projects

        base_metrics = AccountMetrics(
            followers_total=followers_total,
            posts_total=posts_total,
            stars_total=stars_sum,
            forks_total=forks_sum,
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
        """Collect metrics across GitLab instances, isolating failures per account."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
