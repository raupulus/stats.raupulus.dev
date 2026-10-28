"""Unit tests for YouTubeCollector using respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from social_stats.collectors.base import CollectorError
from social_stats.collectors.youtube import YOUTUBE_CHANNELS_URL, YouTubeCollector
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.storage.snapshot_repo import SnapshotRepository


@respx.mock
async def test_youtube_batch_multichannel_and_snapshot_deltas(
    snapshot_repo: SnapshotRepository,
) -> None:
    """
    Verify that multiple channels across profiles are fetched in a single HTTP request
    to Google APIs and enriched with 1h/24h snapshot deltas.
    """
    cid_1 = "UC1111111111111111111111"
    cid_2 = "UC2222222222222222222222"

    # Seed historical snapshot 1h ago for cid_1
    import time

    one_hour_ago = int(time.time()) - 3600
    await snapshot_repo.insert_snapshot(
        Platform.YOUTUBE,
        cid_1,
        AccountMetrics(followers_total=15100, posts_total=279, views_total=2_099_700),
        timestamp=one_hour_ago,
    )

    batch_route = respx.get(YOUTUBE_CHANNELS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": cid_1,
                        "statistics": {
                            "subscriberCount": "15200",
                            "videoCount": "280",
                            "viewCount": "2100000",
                            "hiddenSubscriberCount": False,
                        },
                    },
                    {
                        "id": cid_2,
                        "statistics": {
                            "subscriberCount": "3300",
                            "videoCount": "60",
                            "viewCount": "350120",
                            "hiddenSubscriberCount": False,
                        },
                    },
                ]
            },
        )
    )

    accounts = [
        AccountConfig(id=cid_1, handle="@raupulus", account_key=cid_1, platform="youtube"),
        AccountConfig(id=cid_2, handle="@raupulus_live", account_key=cid_2, platform="youtube"),
    ]

    collector = YouTubeCollector(api_key="test_google_key", snapshot_repo=snapshot_repo)
    results = await collector.collect_batch(accounts)

    assert batch_route.call_count == 1
    request = batch_route.calls[0].request
    assert request.url.params["id"] == f"{cid_1},{cid_2}"

    assert results[cid_1].followers_total == 15200
    assert results[cid_1].posts_total == 280
    assert results[cid_1].views_total == 2_100_000
    assert results[cid_1].views_last_1h == 300
    assert results[cid_1].window_1h_complete is True

    assert results[cid_2].followers_total == 3300
    assert results[cid_2].posts_total == 60
    assert results[cid_2].views_total == 350_120


@respx.mock
async def test_youtube_handle_resolution_and_missing_channel() -> None:
    """
    Verify @handle resolution caching and graceful handling when a channel is missing
    or has hiddenSubscriberCount=True.
    """
    resolved_cid = "UC9999999999999999999999"
    missing_cid = "UC0000000000000000000000"

    def youtube_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if "forHandle" in params:
            return httpx.Response(200, json={"items": [{"id": resolved_cid}]})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": resolved_cid,
                        "statistics": {
                            "videoCount": "12",
                            "viewCount": "9800",
                            "hiddenSubscriberCount": True,
                        },
                    }
                ]
            },
        )

    route = respx.get(YOUTUBE_CHANNELS_URL).mock(side_effect=youtube_handler)

    accounts = [
        AccountConfig(handle="@handle_only", account_key="handle_only", platform="youtube"),
        AccountConfig(id=missing_cid, account_key=missing_cid, platform="youtube"),
    ]
    collector = YouTubeCollector(api_key="test_google_key")

    # First run resolves @handle_only (2 calls: 1 handle resolution + 1 batch)
    results = await collector.collect_batch(accounts)
    assert route.call_count == 2
    assert "handle_only" in results
    assert results["handle_only"].followers_total is None
    assert results["handle_only"].views_total == 9800
    assert missing_cid not in results
    assert missing_cid in collector.last_errors

    # Second run uses cached channel_id (only 1 batch call)
    collector.reset_cycle_tracking()
    await collector.collect_batch(accounts)
    assert route.call_count == 3


async def test_youtube_missing_api_key_raises() -> None:
    """Verify clear CollectorError when YOUTUBE_API_KEY is empty."""
    collector = YouTubeCollector(api_key="")
    accounts = [
        AccountConfig(
            id="UC1111111111111111111111",
            account_key="UC1111111111111111111111",
            platform="youtube",
        )
    ]
    with pytest.raises(CollectorError, match="YOUTUBE_API_KEY"):
        await collector.collect_batch(accounts)
