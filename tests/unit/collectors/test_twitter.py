"""Unit tests for TwitterCollector (Level A Syndication + Level B GraphQL with fallback)."""

from __future__ import annotations

import json

import httpx
import respx

from social_stats.collectors.twitter import (
    SYNDICATION_FOLLOWERS_URL,
    TWITTER_GRAPHQL_TWEETS_URL,
    TWITTER_GRAPHQL_USER_URL,
    TwitterCollector,
)
from social_stats.config.profiles import AccountConfig


@respx.mock
async def test_twitter_syndication_level_a_and_snowflake_ordering() -> None:
    """
    Verify Level A Syndication batch followers and timeline __NEXT_DATA__ parsing,
    sorting tweets by snowflake ID descending to ignore older pinned tweets.
    """
    respx.get(SYNDICATION_FOLLOWERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"screen_name": "raupulus", "followers_count": 4320}],
        )
    )

    next_data = {
        "props": {
            "pageProps": {
                "timeline": {
                    "entries": [
                        {
                            "type": "tweet",
                            "content": {
                                "tweet": {
                                    "id_str": "1700000000000000001",  # Older pinned tweet
                                    "created_at": "Wed Oct 01 10:00:00 +0000 2025",
                                    "user": {"statuses_count": 8910},
                                    "favorite_count": 999,
                                    "reply_count": 50,
                                    "retweet_count": 100,
                                    "ext_views": {"count": "50000"},
                                }
                            },
                        },
                        {
                            "type": "tweet",
                            "content": {
                                "tweet": {
                                    "id_str": "1850912345678901234",  # Newer latest tweet
                                    "created_at": "Wed Oct 28 10:15:00 +0000 2026",
                                    "user": {"statuses_count": 8910},
                                    "favorite_count": 64,
                                    "reply_count": 11,
                                    "retweet_count": 7,
                                    "quote_count": 2,
                                    "ext_views": {"count": "1840"},
                                }
                            },
                        },
                    ]
                }
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></body></html>'

    respx.get("https://syndication.twitter.com/srv/timeline-profile/screen-name/raupulus").mock(
        return_value=httpx.Response(200, text=html)
    )

    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="twitter")
    ]
    collector = TwitterCollector()
    results = await collector.collect_batch(accounts)

    assert "raupulus" in results
    m = results["raupulus"]
    assert m.followers_total == 4320
    assert m.posts_total == 8910
    assert m.latest_post is not None
    assert m.latest_post.post_id == "1850912345678901234"
    assert m.latest_post.views == 1840
    assert m.latest_post.likes == 64
    assert m.latest_post.comments == 11
    assert m.latest_post.shares == 9


@respx.mock
async def test_twitter_level_b_graphql_and_fallback_to_level_a_on_401() -> None:
    """
    Verify Level B GraphQL works when cookies are valid, and transparently falls back
    to Level A Syndication when GraphQL returns HTTP 401/403/429.
    """
    # 1. Level B GraphQL returns 401 Unauthorized -> triggers fallback to Level A
    respx.get(TWITTER_GRAPHQL_USER_URL).mock(
        return_value=httpx.Response(401, json={"errors": [{"message": "Invalid token"}]})
    )
    respx.get(SYNDICATION_FOLLOWERS_URL).mock(
        return_value=httpx.Response(
            200,
            json=[{"screen_name": "raupulus", "followers_count": 4325}],
        )
    )
    respx.get("https://syndication.twitter.com/srv/timeline-profile/screen-name/raupulus").mock(
        return_value=httpx.Response(
            200,
            json={
                "props": {
                    "pageProps": {
                        "timeline": {
                            "entries": [
                                {
                                    "content": {
                                        "tweet": {
                                            "id_str": "1850999999999999999",
                                            "user": {"statuses_count": 8912},
                                            "favorite_count": 30,
                                            "reply_count": 5,
                                            "retweet_count": 4,
                                            "ext_views": {"count": "920"},
                                        }
                                    }
                                }
                            ]
                        }
                    }
                }
            },
        )
    )

    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="twitter")
    ]
    collector = TwitterCollector(auth_token_cookie="expired_auth", ct0_cookie="expired_ct0")
    results = await collector.collect_batch(accounts)

    assert "raupulus" in results
    assert results["raupulus"].followers_total == 4325
    assert results["raupulus"].posts_total == 8912
    assert results["raupulus"].latest_post is not None
    assert results["raupulus"].latest_post.views == 920

    # 2. Level B GraphQL succeeds directly when 200 OK
    respx.get(TWITTER_GRAPHQL_USER_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "user": {
                        "result": {
                            "rest_id": "12345",
                            "legacy": {"followers_count": 4400, "statuses_count": 8920},
                        }
                    }
                }
            },
        )
    )
    respx.get(TWITTER_GRAPHQL_TWEETS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "tweets": [
                    {
                        "id_str": "1851000000000000000",
                        "views": {"count": "3100"},
                        "legacy": {
                            "created_at": "Wed Oct 28 12:00:00 +0000 2026",
                            "favorite_count": 120,
                            "reply_count": 18,
                            "retweet_count": 15,
                            "quote_count": 3,
                        },
                    }
                ]
            },
        )
    )

    results_b = await collector.collect_batch(accounts)
    assert results_b["raupulus"].followers_total == 4400
    assert results_b["raupulus"].latest_post is not None
    assert results_b["raupulus"].latest_post.views == 3100
    assert results_b["raupulus"].latest_post.shares == 18


@respx.mock
async def test_twitter_public_page_fallback() -> None:
    """Verify that when Syndication fails (e.g. 429), collector falls back to public page."""
    respx.get(SYNDICATION_FOLLOWERS_URL).mock(return_value=httpx.Response(429))
    respx.get("https://syndication.twitter.com/srv/timeline-profile/screen-name/raupulus").mock(
        return_value=httpx.Response(429)
    )

    mock_html = """
    <html>
      <body>
        <a href="/raupulus/verified_followers">
          <div><span>1,303</span> <span>Followers</span></div>
        </a>
        <script>tweets:4157</script>
      </body>
    </html>
    """
    respx.get("https://x.com/raupulus").mock(
        return_value=httpx.Response(200, text=mock_html)
    )

    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="twitter")
    ]
    async with httpx.AsyncClient() as client:
        collector = TwitterCollector(http_client=client)
        results = await collector.collect_batch(accounts)

    assert "raupulus" in results
    assert results["raupulus"].followers_total == 1303
    assert results["raupulus"].posts_total == 4157
