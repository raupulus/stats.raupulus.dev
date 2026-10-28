"""Unit tests for InstagramCollector (Level A Graph API + Level B Web Profile fallback)."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.instagram import (
    IG_GRAPH_BASE_URL,
    IG_WEB_PROFILE_URL,
    InstagramCollector,
)
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings


@respx.mock
async def test_instagram_level_a_graph_api_and_fallback_to_level_b() -> None:
    """
    Verify:
    - Level A Meta Graph API extracts followers_count, media_count, and Reel play_count.
    - When Level A returns HTTP 403/429 (or no token is configured), collector falls back
      transparently to Level B (web_profile_info).
    """
    settings = Settings(
        ig_main_user_id="17841401234567",
        ig_main_access_token="system_user_token_forever",
    )

    graph_route = respx.get(f"{IG_GRAPH_BASE_URL}/17841401234567").mock(
        return_value=httpx.Response(
            200,
            json={
                "followers_count": 2890,
                "media_count": 145,
                "media": {
                    "data": [
                        {
                            "id": "17982345678901234",
                            "permalink": "https://www.instagram.com/reel/DBxxxx/",
                            "timestamp": "2026-10-27T18:00:00+0000",
                            "media_type": "REELS",
                            "like_count": 135,
                            "comments_count": 14,
                            "play_count": 1420,
                        }
                    ]
                },
            },
        )
    )

    accounts = [
        AccountConfig(
            handle="raupulus",
            account_key="raupulus",
            credentials_ref="MAIN",
            platform="instagram",
        )
    ]

    collector = InstagramCollector(settings=settings)
    results = await collector.collect_batch(accounts)

    assert graph_route.call_count == 1
    m = results["raupulus"]
    assert m.followers_total == 2890
    assert m.posts_total == 145
    assert m.latest_post is not None
    assert m.latest_post.post_id == "17982345678901234"
    assert m.latest_post.views == 1420
    assert m.latest_post.likes == 135
    assert m.latest_post.comments == 14

    # Simulate Level A returning 429 Too Many Requests -> automatic fallback to Level B
    respx.get(f"{IG_GRAPH_BASE_URL}/17841401234567").mock(
        return_value=httpx.Response(429, json={"error": {"message": "Rate limit"}})
    )
    web_route = respx.get(IG_WEB_PROFILE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "user": {
                        "edge_followed_by": {"count": 2895},
                        "edge_owner_to_timeline_media": {
                            "count": 146,
                            "edges": [
                                {
                                    "node": {
                                        "id": "3488990011",
                                        "shortcode": "DBzzzz",
                                        "taken_at_timestamp": 1_760_000_000,
                                        "is_video": True,
                                        "video_view_count": 980,
                                        "edge_liked_by": {"count": 88},
                                        "edge_media_to_comment": {"count": 9},
                                    }
                                }
                            ],
                        },
                    }
                }
            },
        )
    )

    results_fb = await collector.collect_batch(accounts)
    assert web_route.call_count == 1
    m_fb = results_fb["raupulus"]
    assert m_fb.followers_total == 2895
    assert m_fb.posts_total == 146
    assert m_fb.latest_post is not None
    assert m_fb.latest_post.views == 980
    assert m_fb.latest_post.likes == 88
    assert m_fb.latest_post.comments == 9


async def test_instagram_level_b_uses_curl_cffi_when_enabled(monkeypatch) -> None:
    """
    Verify that when use_curl_cffi=True (production default in build_default_collectors)
    and no external httpx client is injected, Level B uses curl_cffi AsyncSession
    with impersonate='chrome124'.
    """
    captured_calls: list[dict[str, object]] = []

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "user": {
                        "edge_followed_by": {"count": 3100},
                        "edge_owner_to_timeline_media": {
                            "count": 150,
                            "edges": [],
                        },
                    }
                }
            }

    class _FakeAsyncSession:
        def __init__(self, **kwargs: object) -> None:
            captured_calls.append(dict(kwargs))

        async def __aenter__(self) -> _FakeAsyncSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, **kwargs: object) -> _FakeResponse:
            captured_calls.append({"url": url, **kwargs})
            return _FakeResponse()

    monkeypatch.setattr("social_stats.collectors.instagram.AsyncSession", _FakeAsyncSession)

    accounts = [
        AccountConfig(
            handle="raupulus",
            account_key="raupulus",
            platform="instagram",
        )
    ]
    collector = InstagramCollector(settings=Settings(), use_curl_cffi=True)
    results = await collector.collect_batch(accounts)

    assert len(captured_calls) == 2
    assert captured_calls[0]["impersonate"] == "chrome124"
    assert captured_calls[1]["url"] == IG_WEB_PROFILE_URL
    assert results["raupulus"].followers_total == 3100
    assert results["raupulus"].posts_total == 150

