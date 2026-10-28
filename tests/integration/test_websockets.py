"""Integration tests for Read-Only WebSocket streams (/ws/stats and /ws/profiles/{id})."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from social_stats.collectors.base import BaseCollector
from social_stats.config.profiles import AccountConfig, ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.main import create_app
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics
from social_stats.services.aggregator import ProfileAggregator
from social_stats.services.scheduler import CollectorScheduler
from social_stats.services.ws_manager import WSManager
from social_stats.storage.database import Database
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import StateStore


class _StubYouTubeCollector(BaseCollector):
    platform = Platform.YOUTUBE

    def __init__(self, payload_by_key: dict[str, AccountMetrics]) -> None:
        super().__init__()
        self.payload_by_key = payload_by_key

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        return {
            acc.account_key: self.payload_by_key[acc.account_key]
            for acc in accounts
            if acc.account_key in self.payload_by_key
        }


def test_websocket_snapshot_and_profile_isolated_updates(
    sample_registry: ProfilesRegistry,
) -> None:
    """
    Verify:
    - Client on WS /ws/stats?profile=raupulus receives initial snapshot for raupulus.
    - Client on WS /ws/stats (global) receives initial snapshot for all profiles.
    - Updating a raupulus YouTube channel pushes metric_update to BOTH clients.
    - Updating a proyecto_secundario YouTube channel pushes metric_update ONLY to global client.
    - Incoming messages sent by clients are ignored without mutating state.
    """
    db = Database(":memory:")
    store = StateStore(db)
    snapshot_repo = SnapshotRepository(db)
    aggregator = ProfileAggregator(sample_registry, store)
    ws_manager = WSManager(aggregator, heartbeat_interval=3600.0)

    app = create_app(
        settings=Settings(),
        registry=sample_registry,
        db=db,
        state_store=store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        ws_manager=ws_manager,
        enable_scheduler=False,
    )

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/stats") as ws_global,
        client.websocket_connect("/ws/stats?profile=raupulus") as ws_raupulus,
    ):
        # 1. Both receive immediate snapshot
        snap_global = ws_global.receive_json()
        assert snap_global["event"] == "snapshot"
        assert snap_global["scope"]["profile_id"] is None
        assert "raupulus" in snap_global["data"]["profiles"]
        assert "proyecto_secundario" in snap_global["data"]["profiles"]

        snap_raup = ws_raupulus.receive_json()
        assert snap_raup["event"] == "snapshot"
        assert snap_raup["scope"]["profile_id"] == "raupulus"
        assert snap_raup["data"]["profile_id"] == "raupulus"

        # 2. Client sends arbitrary message -> ignored, Read-Only
        ws_raupulus.send_text('{"action": "mutate", "followers": 999999}')

        # 3. Simulate update on raupulus channel (UC1111111111111111111111)
        stub_collector = _StubYouTubeCollector(
            {
                "UC1111111111111111111111": AccountMetrics(
                    followers_total=15210,
                    posts_total=280,
                    views_total=2_100_050,
                )
            }
        )
        scheduler = CollectorScheduler(
            settings=Settings(),
            registry=sample_registry,
            collectors={Platform.YOUTUBE: stub_collector},
            snapshot_repo=snapshot_repo,
            state_store=store,
            aggregator=aggregator,
            on_metric_update=ws_manager.broadcast_update,
            on_status_change=ws_manager.broadcast_collector_status,
        )

        raup_acc = sample_registry.profiles["raupulus"].accounts["youtube"][0]
        assert client.portal is not None
        client.portal.call(
            scheduler.run_collector_once,
            stub_collector,
            [raup_acc],
        )

        # Both global and raupulus clients receive metric_update
        upd_global = ws_global.receive_json()
        assert upd_global["event"] == "metric_update"
        assert upd_global["data"]["profile_id"] == "raupulus"
        assert upd_global["data"]["changes"]["followers_total"]["current"] == 15210

        upd_raup = ws_raupulus.receive_json()
        assert upd_raup["event"] == "metric_update"
        assert upd_raup["data"]["profile_id"] == "raupulus"
        assert upd_raup["data"]["account_key"] == "UC1111111111111111111111"

        # 4. Simulate update ONLY on proyecto_secundario channel (UC4444444444444444444444)
        stub_collector.payload_by_key = {
            "UC4444444444444444444444": AccountMetrics(
                followers_total=955,
                posts_total=16,
                views_total=12_500,
            )
        }
        sec_acc = sample_registry.profiles["proyecto_secundario"].accounts["youtube"][0]
        client.portal.call(
            scheduler.run_collector_once,
            stub_collector,
            [sec_acc],
        )

        # Global client receives the proyecto_secundario update
        upd_global_sec = ws_global.receive_json()
        assert upd_global_sec["event"] == "metric_update"
        assert upd_global_sec["data"]["profile_id"] == "proyecto_secundario"

        # Trigger a heartbeat and verify the next message received by ws_raupulus is heartbeat
        # (proving ws_raupulus NEVER received the proyecto_secundario metric_update)
        client.portal.call(
            ws_manager.broadcast_heartbeat,
            120,
        )
        next_raup_msg = ws_raupulus.receive_json()
        assert next_raup_msg["event"] == "heartbeat"
        assert next_raup_msg["data"]["uptime_seconds"] == 120


def test_websocket_unknown_profile_and_flood_protection(
    sample_registry: ProfilesRegistry,
) -> None:
    """
    Verify:
    - Connecting to a nonexistent profile closes with code 4004.
    - Flooding >10 incoming messages per minute closes with code 1008.
    """
    db = Database(":memory:")
    store = StateStore(db)
    snapshot_repo = SnapshotRepository(db)
    aggregator = ProfileAggregator(sample_registry, store)
    ws_manager = WSManager(aggregator, heartbeat_interval=3600.0)

    app = create_app(
        settings=Settings(),
        registry=sample_registry,
        db=db,
        state_store=store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        ws_manager=ws_manager,
        enable_scheduler=False,
    )

    with TestClient(app) as client:
        # Unknown profile -> 4004
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws/profiles/no_existe") as ws_bad,
        ):
            ws_bad.receive_json()
        assert exc_info.value.code == 4004

        # Flood protection (>10 messages/minute) -> 1008
        with (
            pytest.raises(WebSocketDisconnect) as flood_exc,
            client.websocket_connect("/ws/profiles/raupulus") as ws_flood,
        ):
            snap = ws_flood.receive_json()
            assert snap["event"] == "snapshot"
            for i in range(12):
                ws_flood.send_text(f"ping-{i}")
            ws_flood.receive_json()
        assert flood_exc.value.code == 1008


async def test_ws_manager_send_timeout_disconnects_stalled_client_without_blocking(
    aggregator: ProfileAggregator,
) -> None:
    """
    Verify that a stalled WebSocket client whose send_json hangs longer than send_timeout
    is automatically timed out and disconnected by WSManager without blocking broadcasts
    to healthy subscribers.
    """
    import asyncio
    from unittest.mock import MagicMock

    ws_manager = WSManager(aggregator, heartbeat_interval=3600.0, send_timeout=0.05)

    stalled_ws = MagicMock()

    async def _stalled_send(payload: object) -> None:
        await asyncio.sleep(10.0)

    stalled_ws.send_json = _stalled_send

    healthy_messages: list[object] = []
    healthy_ws = MagicMock()

    async def _healthy_send(payload: object) -> None:
        healthy_messages.append(payload)

    healthy_ws.send_json = _healthy_send

    # Register both subscribers directly
    from social_stats.services.ws_manager import WSSubscription

    sub_stalled = WSSubscription(websocket=stalled_ws, profile_id=None)
    sub_healthy = WSSubscription(websocket=healthy_ws, profile_id=None)
    ws_manager._subscriptions.add(sub_stalled)
    ws_manager._ws_to_sub[stalled_ws] = sub_stalled
    ws_manager._subscriptions.add(sub_healthy)
    ws_manager._ws_to_sub[healthy_ws] = sub_healthy

    assert ws_manager.active_connections_count == 2

    # Broadcast heartbeat -> should complete quickly (~0.05s) and disconnect stalled_ws
    await asyncio.wait_for(ws_manager.broadcast_heartbeat(uptime_seconds=42), timeout=0.5)

    assert len(healthy_messages) == 1
    assert ws_manager.active_connections_count == 1
    assert sub_stalled not in ws_manager._subscriptions
    assert sub_healthy in ws_manager._subscriptions


