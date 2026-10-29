"""Unit tests for GitHubCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.github import GitHubCollector
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings


@respx.mock
async def test_github_pagination_stars_forks_and_bearer_header() -> None:
    """
    Verify GitHubCollector aggregates stargazers and forks across paginated
    repository pages and sends GITHUB_TOKEN strictly via Authorization header.
    """
    user_route = respx.get("https://api.github.com/users/raupulus").mock(
        return_value=httpx.Response(
            200,
            json={
                "login": "raupulus",
                "followers": 152,
                "public_repos": 102,
            },
        )
    )

    page1_repos = [
        {
            "id": 9001,
            "name": "social-stats-api",
            "html_url": "https://github.com/raupulus/social-stats-api",
            "pushed_at": "2026-10-29T08:00:00Z",
            "stargazers_count": 42,
            "forks_count": 7,
            "open_issues_count": 2,
        }
    ] + [
        {
            "id": 1000 + idx,
            "name": f"repo-{idx}",
            "html_url": f"https://github.com/raupulus/repo-{idx}",
            "pushed_at": "2026-10-01T00:00:00Z",
            "stargazers_count": 3,
            "forks_count": 1,
            "open_issues_count": 0,
        }
        for idx in range(99)
    ]
    page2_repos = [
        {
            "id": 2001,
            "name": "repo-extra-1",
            "html_url": "https://github.com/raupulus/repo-extra-1",
            "stargazers_count": 25,
            "forks_count": 1,
        },
        {
            "id": 2002,
            "name": "repo-extra-2",
            "html_url": "https://github.com/raupulus/repo-extra-2",
            "stargazers_count": 6,
            "forks_count": 0,
        },
    ]

    def repos_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer ghp_test_readonly_token"
        assert "ghp_test_readonly_token" not in str(request.url)
        page = request.url.params.get("page")
        if page == "1":
            return httpx.Response(200, json=page1_repos)
        if page == "2":
            return httpx.Response(200, json=page2_repos)
        return httpx.Response(200, json=[])

    respx.get("https://api.github.com/users/raupulus/repos").mock(side_effect=repos_handler)
    respx.get("https://api.github.com/users/missing_org").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    settings = Settings(github_token="ghp_test_readonly_token", _env_file=None)  # type: ignore[call-arg]
    collector = GitHubCollector(settings=settings)

    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="github"),
        AccountConfig(handle="missing_org", account_key="missing_org", platform="github"),
    ]
    results = await collector.collect_batch(accounts)

    assert user_route.called
    assert user_route.calls[0].request.headers.get("Authorization") == "Bearer ghp_test_readonly_token"

    assert "raupulus" in results
    m = results["raupulus"]
    assert m.followers_total == 152
    assert m.posts_total == 102
    assert m.stars_total == 42 + (99 * 3) + 25 + 6  # 370
    assert m.forks_total == 7 + (99 * 1) + 1 + 0  # 107
    assert m.latest_post is not None
    assert m.latest_post.post_id == "9001"
    assert m.latest_post.likes == 42
    assert m.latest_post.shares == 7

    assert "missing_org" not in results
    assert "missing_org" in collector.last_errors
    assert "404" in collector.last_errors["missing_org"]
    assert "ghp_test_readonly_token" not in collector.last_errors["missing_org"]
