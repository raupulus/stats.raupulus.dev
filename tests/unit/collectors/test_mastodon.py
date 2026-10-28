"""Unit tests for MastodonCollector using respx."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.mastodon import MastodonCollector
from social_stats.config.profiles import AccountConfig


@respx.mock
async def test_mastodon_multi_instance_and_partial_failure_isolation() -> None:
    """
    Verify MastodonCollector queries multiple instances and isolates an instance
    failure without aborting healthy instances.
    """
    respx.get("https://mastodon.social/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "10987654321",
                "acct": "raupulus",
                "followers_count": 890,
                "statuses_count": 412,
            },
        )
    )
    respx.get("https://mastodon.social/api/v1/accounts/10987654321/statuses").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "113344556677",
                    "url": "https://mastodon.social/@raupulus/113344556677",
                    "created_at": "2026-10-28T09:30:00.000Z",
                    "favourites_count": 19,
                    "replies_count": 3,
                    "reblogs_count": 7,
                }
            ],
        )
    )

    # Simulate fosstodon.org returning HTTP 503 Service Unavailable
    respx.get("https://fosstodon.org/api/v1/accounts/lookup").mock(
        return_value=httpx.Response(503, json={"error": "Service Unavailable"})
    )

    accounts = [
        AccountConfig(
            instance="mastodon.social",
            handle="raupulus",
            account_key="raupulus@mastodon.social",
            platform="mastodon",
        ),
        AccountConfig(
            instance="fosstodon.org",
            handle="proyecto",
            account_key="proyecto@fosstodon.org",
            platform="mastodon",
        ),
    ]

    collector = MastodonCollector()
    results = await collector.collect_batch(accounts)

    assert "raupulus@mastodon.social" in results
    m = results["raupulus@mastodon.social"]
    assert m.followers_total == 890
    assert m.posts_total == 412
    assert m.latest_post is not None
    assert m.latest_post.post_id == "113344556677"
    assert m.latest_post.likes == 19
    assert m.latest_post.comments == 3
    assert m.latest_post.shares == 7

    # Failed instance was isolated and recorded in collector.last_errors
    assert "proyecto@fosstodon.org" not in results
    assert "proyecto@fosstodon.org" in collector.last_errors
    assert "503" in collector.last_errors["proyecto@fosstodon.org"]
