"""Unit tests for GitLabCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.gitlab import GitLabCollector
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings


@respx.mock
async def test_gitlab_public_xhr_followers_fallback_and_projects_aggregation() -> None:
    """
    Verify GitLabCollector falls back cleanly to /users/{handle}/followers.json
    when /api/v4/users/{id} returns HTTP 403 (as on unauthenticated gitlab.com),
    and sums star_count and forks_count across public projects.
    """
    respx.get("https://gitlab.com/api/v4/users").mock(
        return_value=httpx.Response(200, json=[{"id": 512475, "username": "raupulus"}])
    )
    respx.get("https://gitlab.com/api/v4/users/512475").mock(
        return_value=httpx.Response(403, json={"message": "403 Forbidden"})
    )
    respx.get("https://gitlab.com/users/raupulus/followers.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "html": (
                    '<div class="gl-card gl-p-4">User 1</div>'
                    '<div class="gl-card gl-p-4">User 2</div>'
                    '<div class="gl-card gl-p-4">User 3</div>'
                )
            },
        )
    )
    respx.get("https://gitlab.com/api/v4/users/512475/projects").mock(
        return_value=httpx.Response(
            200,
            headers={"x-total": "129", "x-next-page": ""},
            json=[
                {
                    "id": 7711,
                    "path": "dotfiles",
                    "web_url": "https://gitlab.com/raupulus/dotfiles",
                    "last_activity_at": "2026-10-28T15:00:00.000Z",
                    "star_count": 100,
                    "forks_count": 9,
                    "open_issues_count": 1,
                },
                {
                    "id": 7712,
                    "path": "scripts",
                    "web_url": "https://gitlab.com/raupulus/scripts",
                    "last_activity_at": "2026-10-20T10:00:00.000Z",
                    "star_count": 24,
                    "forks_count": 2,
                    "open_issues_count": 0,
                },
            ],
        )
    )

    collector = GitLabCollector()
    acc = AccountConfig(
        instance="gitlab.com",
        handle="raupulus",
        account_key="raupulus@gitlab.com",
        platform="gitlab",
    )
    results = await collector.collect_batch([acc])

    assert "raupulus@gitlab.com" in results
    m = results["raupulus@gitlab.com"]
    assert m.followers_total == 3
    assert m.posts_total == 129
    assert m.stars_total == 124
    assert m.forks_total == 11
    assert m.latest_post is not None
    assert m.latest_post.post_id == "7711"
    assert m.latest_post.likes == 100
    assert m.latest_post.shares == 9


@respx.mock
async def test_gitlab_authenticated_token_uses_direct_user_detail() -> None:
    """
    Verify GitLabCollector sends PRIVATE-TOKEN header when GITLAB_TOKEN is set
    and reads followers directly from /api/v4/users/{id}.
    """
    respx.get("https://git.example.org/api/v4/users").mock(
        return_value=httpx.Response(200, json=[{"id": 42, "username": "dev"}])
    )
    detail_route = respx.get("https://git.example.org/api/v4/users/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "followers": 19})
    )
    respx.get("https://git.example.org/api/v4/users/42/projects").mock(
        return_value=httpx.Response(
            200,
            headers={"x-total": "1", "x-next-page": ""},
            json=[{"id": 10, "star_count": 8, "forks_count": 1}],
        )
    )

    settings = Settings(gitlab_token="glpat_secret_token", _env_file=None)  # type: ignore[call-arg]
    collector = GitLabCollector(settings=settings)
    acc = AccountConfig(
        instance="git.example.org",
        handle="dev",
        account_key="dev@git.example.org",
        platform="gitlab",
    )
    results = await collector.collect_batch([acc])

    assert detail_route.called
    assert detail_route.calls[0].request.headers.get("PRIVATE-TOKEN") == "glpat_secret_token"
    assert results["dev@git.example.org"].followers_total == 19
    assert results["dev@git.example.org"].stars_total == 8
