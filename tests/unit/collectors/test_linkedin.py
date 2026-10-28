"""Unit tests for LinkedInCollector (disabled by default, organization API, and personal Voyager)."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.linkedin import (
    LINKEDIN_ORG_FOLLOWERS_URL,
    LINKEDIN_ORG_POSTS_URL,
    LINKEDIN_VOYAGER_PROFILE_URL,
    LinkedInCollector,
)
from social_stats.config.profiles import AccountConfig, ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.models.enums import CollectorStatus, Platform
from social_stats.services.aggregator import ProfileAggregator
from social_stats.services.scheduler import CollectorScheduler
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore


async def test_linkedin_unconfigured_marks_disabled_without_error(
    memory_db: Database,
    snapshot_repo: SnapshotRepository,
) -> None:
    """
    Verify that when LinkedIn credentials are not provided in .env, an enabled
    LinkedIn account is marked DISABLED in StateStore without triggering errors.
    """
    registry = ProfilesRegistry.model_validate(
        {
            "version": "1.0",
            "profiles": {
                "raupulus": {
                    "name": "Personal",
                    "accounts": {
                        "linkedin": [
                            {
                                "handle": "raupulus",
                                "account_type": "personal",
                                "enabled": True,
                            }
                        ]
                    },
                }
            },
        }
    )
    store = StateStore(memory_db)
    await store.initialize_from_config_and_db(registry)
    aggregator = ProfileAggregator(registry, store)

    collector = LinkedInCollector(access_token="", li_at_cookie="")
    scheduler = CollectorScheduler(
        settings=Settings(),
        registry=registry,
        collectors={Platform.LINKEDIN: collector},
        snapshot_repo=snapshot_repo,
        state_store=store,
        aggregator=aggregator,
    )

    li_accounts = registry.get_unique_accounts_by_platform()["linkedin"]
    failures = await scheduler.run_collector_once(collector, li_accounts)
    assert failures == 0

    state = store.get_account_state(Platform.LINKEDIN, "raupulus")
    assert state is not None
    assert state.status == CollectorStatus.DISABLED


@respx.mock
async def test_linkedin_organization_and_personal_modes() -> None:
    """Verify both organization REST API mode and personal Voyager API mode."""
    respx.get(LINKEDIN_ORG_FOLLOWERS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "followerCounts": {
                            "organicFollowerCount": 1400,
                            "paidFollowerCount": 50,
                        }
                    }
                ]
            },
        )
    )
    respx.get(LINKEDIN_ORG_POSTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "paging": {"total": 75},
                "elements": [
                    {
                        "id": "urn:li:share:99887766",
                        "publishedAt": 1_760_000_000_000,
                        "socialDetail": {
                            "impressionCount": 3200,
                            "likeCount": 84,
                            "commentCount": 12,
                            "shareCount": 6,
                        },
                    }
                ],
            },
        )
    )

    respx.get(LINKEDIN_VOYAGER_PROFILE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "followerCount": 2150,
                        "activityCount": 130,
                        "latestActivity": {
                            "id": "urn:li:activity:11223344",
                            "views": 1100,
                            "likes": 45,
                            "comments": 7,
                            "shares": 3,
                        },
                    }
                ]
            },
        )
    )

    accounts = [
        AccountConfig(
            handle="12345678",
            account_key="12345678",
            account_type="organization",
            platform="linkedin",
        ),
        AccountConfig(
            handle="raupulus",
            account_key="raupulus",
            account_type="personal",
            platform="linkedin",
        ),
    ]

    collector = LinkedInCollector(
        access_token="org_oauth_token",
        li_at_cookie="personal_li_at_cookie",
    )
    results = await collector.collect_batch(accounts)

    org_m = results["12345678"]
    assert org_m.followers_total == 1450
    assert org_m.posts_total == 75
    assert org_m.latest_post is not None
    assert org_m.latest_post.views == 3200
    assert org_m.latest_post.likes == 84

    pers_m = results["raupulus"]
    assert pers_m.followers_total == 2150
    assert pers_m.posts_total == 130
    assert pers_m.latest_post is not None
    assert pers_m.latest_post.views == 1100
    assert pers_m.latest_post.likes == 45
