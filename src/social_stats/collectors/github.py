"""GitHub REST API v3 collector (followers, public repositories, total stars, and forks)."""

from __future__ import annotations

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

GITHUB_API_BASE = "https://api.github.com"
MAX_REPO_PAGES = 20


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class GitHubCollector(BaseCollector):
    """
    Collects GitHub user/organization followers, public repository count,
    aggregated stargazers (stars_total), and forks (forks_total).
    Supports optional read-only Personal Access Token via Authorization header.
    """

    platform = Platform.GITHUB
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

    def _build_headers(self, credentials_ref: str | None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.settings is not None:
            token = self.settings.get_github_token(credentials_ref or "MAIN")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _collect_single_account(
        self,
        client: httpx.AsyncClient,
        acc: AccountConfig,
    ) -> AccountMetrics:
        handle = (acc.handle or acc.account_key or "").strip().lstrip("@")
        if not handle:
            raise CollectorError("GitHub account missing handle")

        headers = self._build_headers(acc.credentials_ref)

        user_resp = await client.get(f"{GITHUB_API_BASE}/users/{handle}", headers=headers)
        if user_resp.status_code != 200:
            raise CollectorError(
                f"GitHub user lookup failed for '{handle}' with HTTP {user_resp.status_code}",
                status_code=user_resp.status_code,
            )

        user_data: dict[str, Any] = user_resp.json()
        followers_raw = user_data.get("followers")
        public_repos_raw = user_data.get("public_repos")
        expected_repos = int(public_repos_raw) if isinstance(public_repos_raw, int) else None

        stars_sum = 0
        forks_sum = 0
        counted_repos = 0
        latest_post: LatestPostMetrics | None = None

        if expected_repos != 0:
            for page in range(1, MAX_REPO_PAGES + 1):
                repos_resp = await client.get(
                    f"{GITHUB_API_BASE}/users/{handle}/repos",
                    params={
                        "per_page": 100,
                        "type": "owner",
                        "sort": "pushed",
                        "direction": "desc",
                        "page": page,
                    },
                    headers=headers,
                )
                if repos_resp.status_code != 200:
                    raise CollectorError(
                        f"GitHub repos listing failed for '{handle}' (page {page}) "
                        f"with HTTP {repos_resp.status_code}",
                        status_code=repos_resp.status_code,
                    )

                repos_page: list[dict[str, Any]] = repos_resp.json()
                if not repos_page:
                    break

                if page == 1:
                    top = repos_page[0]
                    repo_id = top.get("id")
                    latest_post = LatestPostMetrics(
                        post_id=str(repo_id) if repo_id is not None else top.get("name"),
                        url=top.get("html_url"),
                        published_at=_parse_iso_datetime(
                            top.get("pushed_at") or top.get("created_at")
                        ),
                        views=None,
                        likes=int(top.get("stargazers_count") or 0),
                        comments=int(top.get("open_issues_count") or 0),
                        shares=int(top.get("forks_count") or 0),
                    )

                for repo in repos_page:
                    stars_sum += int(repo.get("stargazers_count") or 0)
                    forks_sum += int(repo.get("forks_count") or 0)
                counted_repos += len(repos_page)

                if len(repos_page) < 100:
                    break
                if expected_repos is not None and counted_repos >= expected_repos:
                    break

        base_metrics = AccountMetrics(
            followers_total=int(followers_raw) if followers_raw is not None else None,
            posts_total=expected_repos if expected_repos is not None else counted_repos,
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
        """Collect metrics across configured GitHub handles, isolating per-account errors."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
