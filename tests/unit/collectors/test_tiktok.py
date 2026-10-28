"""Unit tests for TikTokCollector (SSR hydration + Display API v2 auto-refresh)."""

from __future__ import annotations

import json

import httpx
import respx

from social_stats.collectors.tiktok import (
    TIKTOK_OAUTH_TOKEN_URL,
    TIKTOK_VIDEO_LIST_URL,
    TikTokCollector,
)
from social_stats.config.profiles import AccountConfig
from social_stats.storage.database import Database


@respx.mock
async def test_tiktok_ssr_rehydration_and_display_api_token_rotation(
    memory_db: Database,
) -> None:
    """
    Verify:
    1. SSR extraction from <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"> parses
       followerCount, videoCount, and latest video playCount/diggCount/commentCount/shareCount.
    2. When an expired Display API token exists in SQLite auth_tokens, TikTokCollector
       automatically refreshes it, persists the rotated token in SQLite, and enriches latest_post.
    """
    rehydration_data = {
        "__DEFAULT_SCOPE__": {
            "webapp.user-detail": {
                "userInfo": {
                    "user": {"id": "998877", "uniqueId": "raupulus"},
                    "stats": {
                        "followerCount": 6450,
                        "videoCount": 92,
                    },
                },
                "itemList": [
                    {
                        "id": "7429991112223334445",
                        "createTime": 1_760_000_000,
                        "stats": {
                            "playCount": 14500,
                            "diggCount": 890,
                            "commentCount": 42,
                            "shareCount": 31,
                        },
                    }
                ],
            }
        }
    }
    html = (
        "<html><head>"
        '<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
        f"{json.dumps(rehydration_data)}"
        "</script></head><body></body></html>"
    )

    respx.get("https://www.tiktok.com/@raupulus").mock(
        return_value=httpx.Response(200, text=html)
    )

    accounts = [
        AccountConfig(handle="raupulus", account_key="raupulus", platform="tiktok")
    ]
    collector = TikTokCollector(
        client_key="tt_key",
        client_secret="tt_secret",
        db=memory_db,
        use_curl_cffi=False,
    )

    # 1. Pure SSR extraction (no OAuth token in DB yet)
    results_ssr = await collector.collect_batch(accounts)
    assert "raupulus" in results_ssr
    m_ssr = results_ssr["raupulus"]
    assert m_ssr.followers_total == 6450
    assert m_ssr.posts_total == 92
    assert m_ssr.latest_post is not None
    assert m_ssr.latest_post.post_id == "7429991112223334445"
    assert m_ssr.latest_post.views == 14500
    assert m_ssr.latest_post.likes == 890
    assert m_ssr.latest_post.comments == 42
    assert m_ssr.latest_post.shares == 31

    # 2. Seed an expired token in SQLite auth_tokens -> verify auto-refresh + Display API v2
    await memory_db.upsert_auth_token(
        provider="tiktok",
        credentials_ref="MAIN",
        access_token="expired_tok",
        refresh_token="refresh_tok_old",
        expires_at=100,  # Already expired
        now_ts=50,
    )

    respx.post(TIKTOK_OAUTH_TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "fresh_tok_2026",
                "refresh_token": "refresh_tok_new",
                "expires_in": 86400,
            },
        )
    )
    respx.post(TIKTOK_VIDEO_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "videos": [
                        {
                            "id": "7429991112223334445",
                            "create_time": 1_760_000_000,
                            "view_count": 15200,
                            "like_count": 910,
                            "comment_count": 45,
                            "share_count": 35,
                        }
                    ]
                }
            },
        )
    )

    results_api = await collector.collect_batch(accounts)
    m_api = results_api["raupulus"]
    assert m_api.latest_post is not None
    assert m_api.latest_post.views == 15200
    assert m_api.latest_post.likes == 910

    # Verify rotated token was persisted in SQLite
    stored = await memory_db.get_auth_token("tiktok", "MAIN")
    assert stored is not None
    assert stored.access_token == "fresh_tok_2026"
    assert stored.refresh_token == "refresh_tok_new"
