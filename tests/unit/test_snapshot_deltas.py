"""Unit tests for SQLite snapshot storage and 1h/24h delta calculation engine."""

from __future__ import annotations

from datetime import UTC, datetime

from social_stats.models.enums import CollectorStatus, Platform
from social_stats.models.metrics import AccountMetrics, AccountState, LatestPostMetrics
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository


async def test_nominal_1h_and_24h_deltas(snapshot_repo: SnapshotRepository) -> None:
    """
    Verify exact mathematical delta calculation when snapshots exist at
    (t0 - 24h) and (t0 - 1h), marking window_1h_complete and window_24h_complete True.
    """
    t0 = 1_760_000_000
    t_minus_24h = t0 - 86400
    t_minus_1h = t0 - 3600
    channel_id = "UC1111111111111111111111"

    await snapshot_repo.insert_snapshot(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=15000, posts_total=278, views_total=2_000_000),
        timestamp=t_minus_24h,
    )
    await snapshot_repo.insert_snapshot(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=15035, posts_total=280, views_total=2_004_500),
        timestamp=t_minus_1h,
    )

    enriched = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=15042, posts_total=280, views_total=2_004_815),
        timestamp=t0,
    )

    assert enriched.followers_last_24h == 42
    assert enriched.views_last_24h == 4815
    assert enriched.views_last_1h == 315
    assert enriched.window_1h_complete is True
    assert enriched.window_24h_complete is True


async def test_cold_start_and_warmup_deltas(snapshot_repo: SnapshotRepository) -> None:
    """
    Verify cold start behavior:
    - Very first snapshot at t0 has deltas = 0 and window_*_complete = False.
    - Snapshot 15 minutes later uses the t0 snapshot as warm-up baseline with window_*_complete = False.
    """
    t0 = 1_760_000_000
    channel_id = "UC2222222222222222222222"

    first = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=3300, posts_total=60, views_total=350_000),
        timestamp=t0,
    )
    assert first.followers_last_24h == 0
    assert first.views_last_24h == 0
    assert first.views_last_1h == 0
    assert first.window_1h_complete is False
    assert first.window_24h_complete is False

    # 15 minutes later (900s)
    t_15m = t0 + 900
    second = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=3304, posts_total=60, views_total=350_120),
        timestamp=t_15m,
    )
    assert second.followers_last_24h == 4
    assert second.views_last_24h == 120
    assert second.views_last_1h == 120
    assert second.window_1h_complete is False
    assert second.window_24h_complete is False


async def test_long_outage_gap_protection(snapshot_repo: SnapshotRepository) -> None:
    """
    Verify that a stale snapshot from 5 days ago (server was powered off)
    is NOT used to compute 1h or 24h deltas upon restart.
    """
    t_now = 1_760_000_000
    t_5_days_ago = t_now - (5 * 86400)
    channel_id = "UC3333333333333333333333"

    await snapshot_repo.insert_snapshot(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=1000, posts_total=10, views_total=50_000),
        timestamp=t_5_days_ago,
    )

    after_restart = await snapshot_repo.enrich_and_record(
        Platform.YOUTUBE,
        channel_id,
        AccountMetrics(followers_total=1200, posts_total=12, views_total=80_000),
        timestamp=t_now,
    )

    assert after_restart.followers_last_24h == 0
    assert after_restart.views_last_24h == 0
    assert after_restart.views_last_1h == 0
    assert after_restart.window_1h_complete is False
    assert after_restart.window_24h_complete is False


async def test_history_and_pruning(
    memory_db: Database, snapshot_repo: SnapshotRepository
) -> None:
    """Verify historical series query, old snapshot pruning, and auth_token / state persistence."""
    t_now = 1_760_000_000
    t_40_days_ago = t_now - (40 * 86400)
    t_12_hours_ago = t_now - (12 * 3600)

    for ts, followers, views in [
        (t_40_days_ago, 900, 10000),
        (t_12_hours_ago, 950, 12000),
        (t_now, 960, 12500),
    ]:
        await snapshot_repo.insert_snapshot(
            Platform.YOUTUBE,
            "UC1111111111111111111111",
            AccountMetrics(
                followers_total=followers,
                posts_total=20,
                views_total=views,
                latest_post=LatestPostMetrics(post_id="v1", views=500),
            ),
            timestamp=ts,
        )

    history_24h = await snapshot_repo.get_history(
        Platform.YOUTUBE,
        "UC1111111111111111111111",
        window_seconds=86400,
        now_ts=t_now,
    )
    assert len(history_24h) == 2
    assert history_24h[0].followers_total == 950
    assert history_24h[1].followers_total == 960
    assert history_24h[1].latest_post_views == 500

    deleted = await snapshot_repo.prune_old_snapshots(retention_days=30, now_ts=t_now)
    assert deleted == 1

    # Verify auth_tokens persistence
    await memory_db.upsert_auth_token(
        provider="tiktok",
        credentials_ref="MAIN",
        access_token="acc_123",
        refresh_token="ref_456",
        expires_at=t_now + 86400,
        now_ts=t_now,
    )
    token = await memory_db.get_auth_token("tiktok", "MAIN")
    assert token is not None
    assert token.access_token == "acc_123"
    assert token.refresh_token == "ref_456"

    # Verify account_latest_state persistence
    dt_now = datetime.fromtimestamp(t_now, tz=UTC)
    sample_state = AccountState(
        platform=Platform.BLUESKY,
        account_key="raupulus.dev",
        handle="raupulus.dev",
        label="Bluesky Personal",
        status=CollectorStatus.HEALTHY,
        last_updated_at=dt_now,
        last_attempt_at=dt_now,
        metrics=AccountMetrics(followers_total=1250, posts_total=620),
    )
    await memory_db.upsert_latest_state(sample_state, consecutive_failures=0)
    loaded = await memory_db.load_all_latest_states()
    assert (Platform.BLUESKY, "raupulus.dev") in loaded
    assert loaded[(Platform.BLUESKY, "raupulus.dev")].state.metrics.followers_total == 1250
    assert await memory_db.check_health() is True
