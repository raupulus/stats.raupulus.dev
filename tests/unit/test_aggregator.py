"""Unit tests for ProfileAggregator, DiffEngine, StateStore, and CollectorScheduler."""

from __future__ import annotations

from datetime import UTC, datetime

from social_stats.collectors.base import BaseCollector, CollectorError
from social_stats.config.profiles import AccountConfig, ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.models.api import CollectorStatusData, MetricUpdateData
from social_stats.models.enums import CollectorStatus, Platform
from social_stats.models.metrics import AccountMetrics, AccountState, LatestPostMetrics
from social_stats.services.aggregator import ProfileAggregator, compute_platform_status
from social_stats.services.scheduler import CollectorScheduler, calculate_backoff_delay
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import DiffEngine, StateStore


async def test_multichannel_youtube_aggregation(
    state_store: StateStore, aggregator: ProfileAggregator
) -> None:
    """
    Verify that a profile with 3 YouTube channels aggregates followers, posts,
    views_total, views_last_24h, and views_last_1h accurately while keeping account breakdown.
    """
    now = datetime(2026, 10, 28, 13, 30, 0, tzinfo=UTC)

    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC1111111111111111111111",
        AccountMetrics(
            followers_total=15200,
            followers_last_24h=35,
            posts_total=280,
            views_total=2_100_000,
            views_last_24h=4120,
            views_last_1h=270,
            window_1h_complete=True,
            window_24h_complete=True,
        ),
        now=now,
    )
    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC2222222222222222222222",
        AccountMetrics(
            followers_total=3300,
            followers_last_24h=7,
            posts_total=60,
            views_total=350_120,
            views_last_24h=770,
            views_last_1h=45,
            window_1h_complete=True,
            window_24h_complete=True,
        ),
        now=now,
    )
    await state_store.update_account_success(
        Platform.YOUTUBE,
        "UC3333333333333333333333",
        AccountMetrics(
            followers_total=1500,
            followers_last_24h=8,
            posts_total=40,
            views_total=50_000,
            views_last_24h=110,
            views_last_1h=15,
            window_1h_complete=True,
            window_24h_complete=True,
        ),
        now=now,
    )

    pstats = aggregator.get_profile_stats("raupulus", now=now)
    assert pstats is not None
    yt_summary = pstats.platforms[Platform.YOUTUBE]

    assert yt_summary.accounts_count == 3
    assert yt_summary.status == CollectorStatus.HEALTHY
    assert yt_summary.followers_total == 15200 + 3300 + 1500
    assert yt_summary.followers_last_24h == 35 + 7 + 8
    assert yt_summary.posts_total == 280 + 60 + 40
    assert yt_summary.views_total == 2_100_000 + 350_120 + 50_000
    assert yt_summary.views_last_24h == 4120 + 770 + 110
    assert yt_summary.views_last_1h == 270 + 45 + 15
    assert len(yt_summary.accounts) == 3

    # Disabled LinkedIn platform should be excluded by default
    assert Platform.LINKEDIN not in pstats.platforms


def test_platform_status_precedence() -> None:
    """Verify deterministic status precedence (healthy, stale, error, disabled)."""

    def make_state(status: CollectorStatus) -> AccountState:
        return AccountState(
            platform=Platform.YOUTUBE,
            account_key="k",
            status=status,
        )

    assert compute_platform_status([]) == CollectorStatus.DISABLED
    assert (
        compute_platform_status([make_state(CollectorStatus.DISABLED)])
        == CollectorStatus.DISABLED
    )
    assert (
        compute_platform_status(
            [make_state(CollectorStatus.HEALTHY), make_state(CollectorStatus.DISABLED)]
        )
        == CollectorStatus.HEALTHY
    )
    assert (
        compute_platform_status(
            [make_state(CollectorStatus.HEALTHY), make_state(CollectorStatus.STALE)]
        )
        == CollectorStatus.STALE
    )
    assert (
        compute_platform_status(
            [make_state(CollectorStatus.HEALTHY), make_state(CollectorStatus.ERROR)]
        )
        == CollectorStatus.STALE
    )
    assert (
        compute_platform_status(
            [make_state(CollectorStatus.ERROR), make_state(CollectorStatus.ERROR)]
        )
        == CollectorStatus.ERROR
    )


def test_diff_engine_new_post_and_incremental_changes() -> None:
    """
    Verify DiffEngine detects a new latest_post.post_id with is_new_latest_post=True
    and baseline previous=0 (no negative delta), and computes normal diffs when post_id is unchanged.
    """
    prev = AccountMetrics(
        followers_total=4320,
        posts_total=8910,
        latest_post=LatestPostMetrics(
            post_id="tweet_old",
            views=10_000,
            likes=500,
            comments=40,
            shares=80,
        ),
    )

    # Same post_id, views and likes increased
    curr_same_post = AccountMetrics(
        followers_total=4325,
        posts_total=8910,
        latest_post=LatestPostMetrics(
            post_id="tweet_old",
            views=10_250,
            likes=512,
            comments=40,
            shares=80,
        ),
    )
    diff_same = DiffEngine.compute_diff(prev, curr_same_post)
    assert diff_same.is_new_latest_post is False
    assert diff_same.changes["followers_total"].delta == 5
    assert diff_same.changes["latest_post.views"].previous == 10_000
    assert diff_same.changes["latest_post.views"].current == 10_250
    assert diff_same.changes["latest_post.views"].delta == 250
    assert diff_same.changes["latest_post.likes"].delta == 12
    assert "latest_post.comments" not in diff_same.changes

    # New post published with fewer views than the old post
    curr_new_post = AccountMetrics(
        followers_total=4325,
        posts_total=8911,
        latest_post=LatestPostMetrics(
            post_id="tweet_new",
            views=85,
            likes=9,
            comments=2,
            shares=1,
        ),
    )
    diff_new = DiffEngine.compute_diff(curr_same_post, curr_new_post)
    assert diff_new.is_new_latest_post is True
    assert diff_new.changes["posts_total"].delta == 1
    assert diff_new.changes["latest_post.views"].previous == 0
    assert diff_new.changes["latest_post.views"].current == 85
    assert diff_new.changes["latest_post.views"].delta == 85
    assert diff_new.changes["latest_post.likes"].delta == 9


class _MockTwitterCollector(BaseCollector):
    platform = Platform.TWITTER

    def __init__(self) -> None:
        super().__init__()
        self.should_fail = False
        self.followers = 4320

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        if self.should_fail:
            raise CollectorError("HTTP 429 Too Many Requests", status_code=429)
        return {
            acc.account_key: AccountMetrics(
                followers_total=self.followers,
                posts_total=8910,
            )
            for acc in accounts
        }


async def test_scheduler_stale_data_preservation_and_recovery(
    memory_db: Database,
    snapshot_repo: SnapshotRepository,
    sample_registry: ProfilesRegistry,
    state_store: StateStore,
    aggregator: ProfileAggregator,
) -> None:
    """
    Verify that when a collector fails after a successful cycle:
    - Status transitions from HEALTHY to STALE.
    - Previous valid metrics are preserved in StateStore and ProfileAggregator.
    - When the collector recovers, status transitions back from STALE to HEALTHY.
    """
    collector = _MockTwitterCollector()
    updates_received: list[MetricUpdateData] = []
    statuses_received: list[CollectorStatusData] = []

    async def on_update(data: MetricUpdateData) -> None:
        updates_received.append(data)

    async def on_status(data: CollectorStatusData) -> None:
        statuses_received.append(data)

    scheduler = CollectorScheduler(
        settings=Settings(),
        registry=sample_registry,
        collectors={Platform.TWITTER: collector},
        snapshot_repo=snapshot_repo,
        state_store=state_store,
        aggregator=aggregator,
        on_metric_update=on_update,
        on_status_change=on_status,
    )

    twitter_accounts = sample_registry.get_unique_accounts_by_platform()["twitter"]
    t1 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)

    # 1. Successful collection
    failures = await scheduler.run_collector_once(collector, twitter_accounts, now=t1)
    assert failures == 0
    assert len(updates_received) == 1
    state_ok = state_store.get_account_state(Platform.TWITTER, "raupulus")
    assert state_ok is not None
    assert state_ok.status == CollectorStatus.HEALTHY
    assert state_ok.metrics.followers_total == 4320

    # 2. Upstream failure (HTTP 429) -> STALE preserving metrics
    collector.should_fail = True
    t2 = datetime(2026, 10, 28, 12, 10, 0, tzinfo=UTC)
    failures = await scheduler.run_collector_once(collector, twitter_accounts, now=t2)
    assert failures == 1
    state_stale = state_store.get_account_state(Platform.TWITTER, "raupulus")
    assert state_stale is not None
    assert state_stale.status == CollectorStatus.STALE
    assert state_stale.metrics.followers_total == 4320
    assert state_stale.last_updated_at == t1
    assert state_stale.last_attempt_at == t2
    assert "429" in (state_stale.error_message or "")
    assert len(statuses_received) == 1
    assert statuses_received[0].previous_status == CollectorStatus.HEALTHY
    assert statuses_received[0].current_status == CollectorStatus.STALE

    # 3. Recovery -> HEALTHY
    collector.should_fail = False
    collector.followers = 4325
    t3 = datetime(2026, 10, 28, 12, 20, 0, tzinfo=UTC)
    failures = await scheduler.run_collector_once(collector, twitter_accounts, now=t3)
    assert failures == 0
    state_recovered = state_store.get_account_state(Platform.TWITTER, "raupulus")
    assert state_recovered is not None
    assert state_recovered.status == CollectorStatus.HEALTHY
    assert state_recovered.metrics.followers_total == 4325
    assert len(statuses_received) == 2
    assert statuses_received[1].previous_status == CollectorStatus.STALE
    assert statuses_received[1].current_status == CollectorStatus.HEALTHY


def test_exponential_backoff_calculation() -> None:
    """Verify exponential backoff formula capped at 3600 seconds."""
    assert calculate_backoff_delay(300, 0, apply_jitter=False) == 300.0
    assert calculate_backoff_delay(300, 1, apply_jitter=False) == 600.0
    assert calculate_backoff_delay(300, 2, apply_jitter=False) == 1200.0
    assert calculate_backoff_delay(300, 5, apply_jitter=False) == 3600.0

    with_jitter = calculate_backoff_delay(300, 0, apply_jitter=True)
    assert 285.0 <= with_jitter <= 315.0


class _PartialBatchCollector(BaseCollector):
    platform = Platform.YOUTUBE

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        # Return only the first account; record an error for the rest
        out: dict[str, AccountMetrics] = {}
        for idx, acc in enumerate(accounts):
            if idx == 0:
                out[acc.account_key] = AccountMetrics(
                    followers_total=1000, posts_total=10, views_total=5000
                )
            else:
                self.record_account_error(acc.account_key, "Channel temporarily unavailable")
        return out


async def test_scheduler_background_lifecycle_and_restart_hydration(
    memory_db: Database,
    snapshot_repo: SnapshotRepository,
    sample_registry: ProfilesRegistry,
) -> None:
    """
    Verify:
    - CollectorScheduler.start() and stop() run background platform and pruning loops cleanly.
    - Partial account failures within a batch mark only missing accounts as failed.
    - StateStore.initialize_from_config_and_db() restores persisted state from SQLite on restart.
    """
    import asyncio

    store1 = StateStore(memory_db)
    await store1.initialize_from_config_and_db(sample_registry)
    agg1 = ProfileAggregator(sample_registry, store1)

    partial_collector = _PartialBatchCollector()
    scheduler = CollectorScheduler(
        settings=Settings(poll_interval_youtube=60),
        registry=sample_registry,
        collectors={Platform.YOUTUBE: partial_collector},
        snapshot_repo=snapshot_repo,
        state_store=store1,
        aggregator=agg1,
    )

    scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    # First YouTube channel succeeded; second channel recorded error
    st_ok = store1.get_account_state(Platform.YOUTUBE, "UC1111111111111111111111")
    assert st_ok is not None
    assert st_ok.status == CollectorStatus.HEALTHY
    assert st_ok.metrics.followers_total == 1000

    st_err = store1.get_account_state(Platform.YOUTUBE, "UC2222222222222222222222")
    assert st_err is not None
    assert st_err.status == CollectorStatus.ERROR
    assert store1.get_consecutive_failures(Platform.YOUTUBE, "UC2222222222222222222222") >= 1

    # Simulate container restart by creating a brand new StateStore against the same SQLite DB
    store2 = StateStore(memory_db)
    await store2.initialize_from_config_and_db(sample_registry)
    restored = store2.get_account_state(Platform.YOUTUBE, "UC1111111111111111111111")
    assert restored is not None
    assert restored.metrics.followers_total == 1000
    assert restored.status == CollectorStatus.HEALTHY

    # Verify that on restart, CollectorScheduler does NOT re-poll the fresh HEALTHY account
    # at t=0, and only retries the account in ERROR state.
    polled_on_restart: list[str] = []

    class _RecordingCollector(BaseCollector):
        platform = Platform.YOUTUBE

        async def collect_batch(
            self, accounts: list[AccountConfig]
        ) -> dict[str, AccountMetrics]:
            for a in accounts:
                polled_on_restart.append(a.account_key)
            return {
                a.account_key: AccountMetrics(
                    followers_total=2000, posts_total=20, views_total=9000
                )
                for a in accounts
            }

    agg2 = ProfileAggregator(sample_registry, store2)
    scheduler2 = CollectorScheduler(
        settings=Settings(poll_interval_youtube=600),
        registry=sample_registry,
        collectors={Platform.YOUTUBE: _RecordingCollector()},
        snapshot_repo=snapshot_repo,
        state_store=store2,
        aggregator=agg2,
    )
    scheduler2.start()
    await asyncio.sleep(0.05)
    await scheduler2.stop()

    assert "UC1111111111111111111111" not in polled_on_restart
    assert "UC2222222222222222222222" in polled_on_restart



class _SnapshotEnrichingCollector(BaseCollector):
    platform = Platform.YOUTUBE

    def __init__(self, snapshot_repo: SnapshotRepository) -> None:
        super().__init__(snapshot_repo=snapshot_repo)

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        out: dict[str, AccountMetrics] = {}
        for acc in accounts:
            raw = AccountMetrics(followers_total=5000, posts_total=50, views_total=100_000)
            out[acc.account_key] = await self.enrich_with_snapshots(acc.account_key, raw)
        return out


async def test_scheduler_propagates_cycle_timestamp_and_prevents_duplicate_snapshots(
    memory_db: Database,
    sample_registry: ProfilesRegistry,
    state_store: StateStore,
    aggregator: ProfileAggregator,
) -> None:
    """
    Verify that when a collector calls self.enrich_with_snapshots() inside collect_batch():
    1. CollectorScheduler propagates its custom `now` timestamp to BaseCollector.
    2. Even if collector.snapshot_repo and scheduler.snapshot_repo are distinct instances on
       the same Database, enrich_and_record is executed only ONCE per account per cycle.
    """
    repo_collector = SnapshotRepository(memory_db)
    repo_scheduler = SnapshotRepository(memory_db)
    collector = _SnapshotEnrichingCollector(snapshot_repo=repo_collector)

    scheduler = CollectorScheduler(
        settings=Settings(),
        registry=sample_registry,
        collectors={Platform.YOUTUBE: collector},
        snapshot_repo=repo_scheduler,
        state_store=state_store,
        aggregator=aggregator,
    )

    custom_now = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
    target_account = sample_registry.profiles["raupulus"].accounts["youtube"][0]

    await scheduler.run_collector_once(collector, [target_account], now=custom_now)

    history = await repo_scheduler.get_history(
        "youtube",
        target_account.account_key,
        window_seconds=3600,
        now_ts=int(custom_now.timestamp()),
    )
    assert len(history) == 1
    assert history[0].timestamp == custom_now


async def test_scheduler_projects_profile_specific_label_in_metric_update(
    memory_db: Database,
) -> None:
    """
    Verify that when the same account is referenced in two profiles with different labels,
    MetricUpdateData emitted for each profile projects that profile's specific label and handle.
    """
    shared_key = "UC9999999999999999999999"
    registry = ProfilesRegistry.model_validate(
        {
            "profiles": {
                "perfil_a": {
                    "name": "Perfil A",
                    "accounts": {
                        "youtube": [
                            {
                                "id": shared_key,
                                "handle": "@handle_a",
                                "label": "Etiqueta Perfil A",
                            }
                        ]
                    },
                },
                "perfil_b": {
                    "name": "Perfil B",
                    "accounts": {
                        "youtube": [
                            {
                                "id": shared_key,
                                "handle": "@handle_b",
                                "label": "Etiqueta Perfil B",
                            }
                        ]
                    },
                },
            }
        }
    )

    store = StateStore(memory_db)
    await store.initialize_from_config_and_db(registry)
    repo = SnapshotRepository(memory_db)
    agg = ProfileAggregator(registry, store)

    updates_by_profile: dict[str, MetricUpdateData] = {}

    async def on_update(data: MetricUpdateData) -> None:
        updates_by_profile[data.profile_id] = data

    collector = _SnapshotEnrichingCollector(snapshot_repo=repo)
    scheduler = CollectorScheduler(
        settings=Settings(),
        registry=registry,
        collectors={Platform.YOUTUBE: collector},
        snapshot_repo=repo,
        state_store=store,
        aggregator=agg,
        on_metric_update=on_update,
    )

    unique_yt = registry.get_unique_accounts_by_platform()["youtube"]
    await scheduler.run_collector_once(collector, unique_yt)

    assert set(updates_by_profile.keys()) == {"perfil_a", "perfil_b"}
    assert updates_by_profile["perfil_a"].account.label == "Etiqueta Perfil A"
    assert updates_by_profile["perfil_a"].account.handle == "@handle_a"
    assert updates_by_profile["perfil_b"].account.label == "Etiqueta Perfil B"
    assert updates_by_profile["perfil_b"].account.handle == "@handle_b"


def test_diff_engine_when_previous_latest_post_is_none() -> None:
    """
    Verify DiffEngine marks is_new_latest_post=True and uses baseline previous=0
    when the previous state had latest_post=None and the current state has a latest_post.
    """
    prev = AccountMetrics(followers_total=100, posts_total=0, latest_post=None)
    curr = AccountMetrics(
        followers_total=105,
        posts_total=1,
        latest_post=LatestPostMetrics(
            post_id="first_post",
            views=50,
            likes=10,
            comments=2,
            shares=1,
        ),
    )
    diff = DiffEngine.compute_diff(prev, curr)
    assert diff.is_new_latest_post is True
    assert diff.changes["latest_post.views"].previous == 0
    assert diff.changes["latest_post.views"].current == 50
    assert diff.changes["latest_post.views"].delta == 50


async def test_aggregator_public_only_filtering_and_keycounter_redaction(
    memory_db: Database,
) -> None:
    """
    Verify that ProfileAggregator with public_only=True:
    - Excludes profiles with public=False and accounts with public=False.
    - Strips error_message and last_attempt_at from AccountState.
    - For KEYCOUNTER, exposes only pulsations_total and clicks_total (setting 1h and today to None).
    """
    registry = ProfilesRegistry.model_validate(
        {
            "profiles": {
                "pub": {
                    "name": "Public Profile",
                    "public": True,
                    "accounts": {
                        "bluesky": [
                            {"handle": "visible.bsky.social", "public": True},
                            {"handle": "hidden.bsky.social", "public": False},
                        ],
                        "keycounter": [
                            {"handle": "raupulus", "public": True},
                        ],
                    },
                },
                "priv": {
                    "name": "Private Profile",
                    "public": False,
                    "accounts": {
                        "bluesky": [
                            {"handle": "secret.bsky.social", "public": True},
                        ]
                    },
                },
            }
        }
    )

    store = StateStore(memory_db)
    await store.initialize_from_config_and_db(registry)
    now = datetime(2026, 10, 28, 14, 0, 0, tzinfo=UTC)

    await store.update_account_success(
        Platform.BLUESKY,
        "visible.bsky.social",
        AccountMetrics(followers_total=500, posts_total=20),
        now=now,
    )
    await store.record_account_failure(
        Platform.BLUESKY,
        "visible.bsky.social",
        "HTTP 502 Bad Gateway",
        now=now,
    )
    await store.update_account_success(
        Platform.BLUESKY,
        "hidden.bsky.social",
        AccountMetrics(followers_total=9000, posts_total=100),
        now=now,
    )
    await store.update_account_success(
        Platform.KEYCOUNTER,
        "raupulus",
        AccountMetrics(
            pulsations_total=12_845_620,
            pulsations_today=15_420,
            pulsations_last_1h=1_850,
            clicks_total=450_120,
            clicks_today=1_200,
            clicks_last_1h=150,
            window_1h_complete=True,
            window_24h_complete=True,
        ),
        now=now,
    )

    agg = ProfileAggregator(registry, store)

    # Private view includes everything
    g_private = agg.get_global_stats(public_only=False, now=now)
    assert "pub" in g_private.profiles
    assert "priv" in g_private.profiles
    assert len(g_private.profiles["pub"].platforms[Platform.BLUESKY].accounts) == 2
    assert (
        g_private.profiles["pub"].platforms[Platform.KEYCOUNTER].pulsations_today
        == 15_420
    )

    # Public view filters private profiles/accounts and redacts keycounter 1h/today + errors
    g_public = agg.get_global_stats(public_only=True, now=now)
    assert list(g_public.profiles.keys()) == ["pub"]
    bsky_pub = g_public.profiles["pub"].platforms[Platform.BLUESKY]
    assert len(bsky_pub.accounts) == 1
    assert bsky_pub.accounts[0].account_key == "visible.bsky.social"
    assert bsky_pub.accounts[0].error_message is None
    assert bsky_pub.accounts[0].last_attempt_at is None
    assert bsky_pub.followers_total == 500

    kc_pub = g_public.profiles["pub"].platforms[Platform.KEYCOUNTER]
    assert kc_pub.pulsations_total == 12_845_620
    assert kc_pub.clicks_total == 450_120
    assert kc_pub.pulsations_today is None
    assert kc_pub.pulsations_last_1h is None
    assert kc_pub.clicks_today is None
    assert kc_pub.clicks_last_1h is None
    kc_acc = kc_pub.accounts[0]
    assert kc_acc.metrics.pulsations_total == 12_845_620
    assert kc_acc.metrics.clicks_total == 450_120
    assert kc_acc.metrics.pulsations_today is None
    assert kc_acc.metrics.pulsations_last_1h is None
    assert kc_acc.metrics.clicks_today is None
    assert kc_acc.metrics.clicks_last_1h is None


async def test_stars_forks_and_twitch_live_aggregation_and_diff(
    memory_db: Database,
) -> None:
    """Verify stars_total, forks_total, is_live, live_viewers aggregation, snapshot history, and DiffEngine."""
    registry = ProfilesRegistry.model_validate(
        {
            "version": "1.0",
            "profiles": {
                "dev": {
                    "name": "Dev",
                    "accounts": {
                        "github": [
                            {"handle": "raupulus"},
                            {"handle": "org_repo"},
                        ],
                        "twitch": [{"handle": "raupulus"}],
                    },
                }
            },
        }
    )
    store = StateStore(memory_db)
    snap_repo = SnapshotRepository(memory_db)
    await store.initialize_from_config_and_db(registry)
    now = datetime(2026, 10, 29, 9, 30, 0, tzinfo=UTC)

    gh1 = await snap_repo.enrich_and_record(
        Platform.GITHUB,
        "raupulus",
        AccountMetrics(
            followers_total=152,
            posts_total=146,
            stars_total=370,
            forks_total=107,
        ),
        timestamp=int(now.timestamp()),
    )
    await store.update_account_success(Platform.GITHUB, "raupulus", gh1, now=now)
    await store.update_account_success(
        Platform.GITHUB,
        "org_repo",
        AccountMetrics(followers_total=10, posts_total=4, stars_total=30, forks_total=3),
        now=now,
    )

    # Twitch starts offline, then transitions to live
    out1 = await store.update_account_success(
        Platform.TWITCH,
        "raupulus",
        AccountMetrics(followers_total=1074, posts_total=1, is_live=False, live_viewers=None),
        now=now,
    )
    assert "is_live" not in out1.diff.changes

    out2 = await store.update_account_success(
        Platform.TWITCH,
        "raupulus",
        AccountMetrics(followers_total=1074, posts_total=1, is_live=True, live_viewers=42),
        now=now,
    )
    assert out2.diff.has_changes
    assert out2.diff.changes["is_live"].delta == 1
    assert out2.diff.changes["live_viewers"].current == 42

    agg = ProfileAggregator(registry, store)
    pstats = agg.get_profile_stats("dev", now=now)
    assert pstats is not None
    gh_sum = pstats.platforms[Platform.GITHUB]
    assert gh_sum.followers_total == 162
    assert gh_sum.posts_total == 150
    assert gh_sum.stars_total == 400
    assert gh_sum.forks_total == 110

    tw_sum = pstats.platforms[Platform.TWITCH]
    assert tw_sum.is_live is True
    assert tw_sum.live_viewers == 42

    history = await snap_repo.get_history(
        Platform.GITHUB, "raupulus", window_seconds=3600, now_ts=int(now.timestamp())
    )
    assert len(history) == 1
    assert history[0].stars_total == 370
    assert history[0].forks_total == 107


