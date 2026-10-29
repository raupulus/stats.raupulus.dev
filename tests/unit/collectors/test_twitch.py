"""Unit tests for TwitchCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.twitch import TwitchCollector
from social_stats.config.profiles import AccountConfig


@respx.mock
async def test_twitch_level_a_helix_oauth_and_live_stream() -> None:
    """
    Verify TwitchCollector exchanges client_credentials in POST body (never URL)
    and queries Helix endpoints for followers, live stream status, and viewers.
    """
    def oauth_handler(request: httpx.Request) -> httpx.Response:
        assert "secret_xyz" not in str(request.url)
        body = request.content.decode("utf-8")
        assert "grant_type=client_credentials" in body
        assert "client_secret=secret_xyz" in body
        return httpx.Response(
            200,
            json={"access_token": "app_tok_123", "expires_in": 3600, "token_type": "bearer"},
        )

    respx.post("https://id.twitch.tv/oauth2/token").mock(side_effect=oauth_handler)
    respx.get("https://api.twitch.tv/helix/users").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "889900", "login": "raupulus"}]})
    )
    respx.get("https://api.twitch.tv/helix/channels/followers").mock(
        return_value=httpx.Response(200, json={"total": 1074, "data": []})
    )
    respx.get("https://api.twitch.tv/helix/streams").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "stream_55",
                        "viewer_count": 47,
                        "started_at": "2026-10-29T08:00:00Z",
                    }
                ]
            },
        )
    )
    respx.get("https://api.twitch.tv/helix/videos").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "v991",
                        "url": "https://www.twitch.tv/videos/v991",
                        "published_at": "2026-10-27T20:00:00Z",
                        "view_count": 320,
                    }
                ]
            },
        )
    )

    collector = TwitchCollector(client_id="cid_abc", client_secret="secret_xyz")
    acc = AccountConfig(handle="raupulus", account_key="raupulus", platform="twitch")
    results = await collector.collect_batch([acc])

    assert "raupulus" in results
    m = results["raupulus"]
    assert m.followers_total == 1074
    assert m.is_live is True
    assert m.live_viewers == 47
    assert m.latest_post is not None
    assert m.latest_post.post_id == "v991"
    assert m.latest_post.views == 320


@respx.mock
async def test_twitch_level_b_public_gql_fallback_offline() -> None:
    """
    Verify TwitchCollector works without credentials via public Twitch GQL
    and accurately reports offline channels (is_live=False, live_viewers=0).
    """
    respx.post("https://gql.twitch.tv/gql").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "user": {
                        "id": "889900",
                        "login": "raupulus",
                        "followers": {"totalCount": 1074},
                        "stream": None,
                        "videos": {
                            "totalCount": 1,
                            "edges": [
                                {
                                    "node": {
                                        "id": "224466",
                                        "viewCount": 158,
                                        "publishedAt": "2026-10-15T19:00:00Z",
                                    }
                                }
                            ],
                        },
                    }
                }
            },
        )
    )

    collector = TwitchCollector()
    acc = AccountConfig(handle="raupulus", account_key="raupulus", platform="twitch")
    results = await collector.collect_batch([acc])

    assert "raupulus" in results
    m = results["raupulus"]
    assert m.followers_total == 1074
    assert m.posts_total == 1
    assert m.is_live is False
    assert m.live_viewers == 0
    assert m.latest_post is not None
    assert m.latest_post.post_id == "224466"
    assert m.latest_post.views == 158
