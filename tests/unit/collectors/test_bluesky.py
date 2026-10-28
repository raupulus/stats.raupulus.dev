"""Unit tests for BlueskyCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.bluesky import (
    BLUESKY_GET_AUTHOR_FEED_URL,
    BLUESKY_GET_PROFILES_URL,
    BlueskyCollector,
)
from social_stats.config.profiles import AccountConfig


@respx.mock
async def test_bluesky_batch_profiles_and_author_feed_filtering() -> None:
    """
    Verify BlueskyCollector fetches profiles in batch, skips reposts in getAuthorFeed,
    and extracts likes, comments, and shares (repostCount + quoteCount).
    """
    profiles_route = respx.get(BLUESKY_GET_PROFILES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "profiles": [
                    {
                        "did": "did:plc:111",
                        "handle": "raupulus.dev",
                        "followersCount": 1250,
                        "postsCount": 620,
                    },
                    {
                        "did": "did:plc:222",
                        "handle": "proyecto.bsky.social",
                        "followersCount": 340,
                        "postsCount": 45,
                    },
                ]
            },
        )
    )

    def feed_handler(request: httpx.Request) -> httpx.Response:
        actor = request.url.params.get("actor")
        if actor == "raupulus.dev":
            return httpx.Response(
                200,
                json={
                    "feed": [
                        {
                            # First item is a repost -> must be skipped
                            "reason": {"$type": "app.bsky.feed.defs#reasonRepost"},
                            "post": {
                                "uri": "at://did:plc:other/app.bsky.feed.post/repost1",
                                "likeCount": 999,
                            },
                        },
                        {
                            "post": {
                                "uri": "at://did:plc:111/app.bsky.feed.post/3l7abc123",
                                "author": {"handle": "raupulus.dev"},
                                "record": {"createdAt": "2026-10-28T11:00:00Z"},
                                "likeCount": 28,
                                "replyCount": 4,
                                "repostCount": 5,
                                "quoteCount": 1,
                            }
                        },
                    ]
                },
            )
        return httpx.Response(200, json={"feed": []})

    respx.get(BLUESKY_GET_AUTHOR_FEED_URL).mock(side_effect=feed_handler)

    accounts = [
        AccountConfig(handle="raupulus.dev", account_key="raupulus.dev", platform="bluesky"),
        AccountConfig(
            handle="proyecto.bsky.social",
            account_key="proyecto.bsky.social",
            platform="bluesky",
        ),
    ]

    collector = BlueskyCollector()
    results = await collector.collect_batch(accounts)

    assert profiles_route.call_count == 1
    assert results["raupulus.dev"].followers_total == 1250
    assert results["raupulus.dev"].posts_total == 620
    latest = results["raupulus.dev"].latest_post
    assert latest is not None
    assert latest.post_id == "at://did:plc:111/app.bsky.feed.post/3l7abc123"
    assert latest.url == "https://bsky.app/profile/raupulus.dev/post/3l7abc123"
    assert latest.likes == 28
    assert latest.comments == 4
    assert latest.shares == 6
    assert latest.views is None

    # Account with empty feed has latest_post = None
    assert results["proyecto.bsky.social"].followers_total == 340
    assert results["proyecto.bsky.social"].latest_post is None
