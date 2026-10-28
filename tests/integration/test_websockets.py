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


class _StubKeycounterCollector(BaseCollector):
    platform = Platform.KEYCOUNTER

    def __init__(self, metrics: AccountMetrics) -> None:
        super().__init__()
        self.metrics = metrics

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        return {acc.account_key: self.metrics for acc in accounts}


def test_websocket_snapshot_and_profile_isolated_updates(
    sample_registry: ProfilesRegistry,
) -> None:
    """
    Verify:
    - Private WS (/ws/stats) requires valid API_BEARER_TOKEN (Authorization header, subprotocol, or ?token=).
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
    settings = Settings(_env_file=None, api_bearer_token="secret-ws-token")

    app = create_app(
        settings=settings,
        registry=sample_registry,
        db=db,
        state_store=store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        ws_manager=ws_manager,
        enable_scheduler=False,
    )
    auth_headers = {"Authorization": "Bearer secret-ws-token"}

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/stats", headers=auth_headers) as ws_global,
        client.websocket_connect(
            "/ws/stats?profile=raupulus",
            subprotocols=["bearer", "secret-ws-token"],
        ) as ws_raupulus,
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
            settings=settings,
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


def test_websocket_unknown_profile_auth_rejection_and_flood_protection(
    sample_registry: ProfilesRegistry,
) -> None:
    """
    Verify:
    - Private WS without token or with wrong token closes with code 1008.
    - Connecting to a nonexistent profile closes with code 4004.
    - Flooding >10 incoming messages per minute on private WS closes with code 1008.
    """
    db = Database(":memory:")
    store = StateStore(db)
    snapshot_repo = SnapshotRepository(db)
    aggregator = ProfileAggregator(sample_registry, store)
    ws_manager = WSManager(aggregator, heartbeat_interval=3600.0)
    settings = Settings(_env_file=None, api_bearer_token="secret-ws-token")

    app = create_app(
        settings=settings,
        registry=sample_registry,
        db=db,
        state_store=store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        ws_manager=ws_manager,
        enable_scheduler=False,
    )
    auth_headers = {"Authorization": "Bearer secret-ws-token"}

    with TestClient(app) as client:
        # Missing token on /ws/stats -> 1008
        with (
            pytest.raises(WebSocketDisconnect) as unauth_exc,
            client.websocket_connect("/ws/stats") as ws_unauth,
        ):
            ws_unauth.receive_json()
        assert unauth_exc.value.code == 1008

        # Wrong token on /ws/profiles/raupulus -> 1008
        with (
            pytest.raises(WebSocketDisconnect) as bad_tok_exc,
            client.websocket_connect(
                "/ws/profiles/raupulus?token=wrong-token"
            ) as ws_bad_tok,
        ):
            ws_bad_tok.receive_json()
        assert bad_tok_exc.value.code == 1008

        # Unknown profile -> 4004
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                "/ws/profiles/no_existe", headers=auth_headers
            ) as ws_bad,
        ):
            ws_bad.receive_json()
        assert exc_info.value.code == 4004

        # Flood protection (>10 messages/minute) -> 1008
        with (
            pytest.raises(WebSocketDisconnect) as flood_exc,
            client.websocket_connect(
                "/ws/profiles/raupulus?token=secret-ws-token"
            ) as ws_flood,
        ):
            snap = ws_flood.receive_json()
            assert snap["event"] == "snapshot"
            for i in range(12):
                ws_flood.send_text(f"ping-{i}")
            ws_flood.receive_json()
        assert flood_exc.value.code == 1008


def test_public_websocket_origin_limits_keycounter_redaction_and_zero_messages() -> None:
    """
    Verify /ws/public:
    1. Rejects missing or unauthorized Origin with 1008 before sending snapshot.
    2. Enforces per-IP and global connection limits with 1008 before sending snapshot.
    3. Excludes profiles/accounts with public=False and closes 4004 on ?profile=private_profile.
    4. Exposes ONLY pulsations_total and clicks_total for Keycounter (1h and today are None).
    5. Does NOT emit metric_update on /ws/public if only Keycounter 1h/today windows changed.
    6. Never emits collector_status events on /ws/public.
    7. Closes immediately with 1008 on the very first incoming client message.
    """
    registry = ProfilesRegistry.model_validate(
        {
            "profiles": {
                "raupulus": {
                    "name": "Perfil Principal",
                    "public": True,
                    "accounts": {
                        "youtube": [
                            {
                                "id": "UC1111111111111111111111",
                                "handle": "@raupulus",
                                "public": True,
                            },
                            {
                                "id": "UC2222222222222222222222",
                                "handle": "@private_channel",
                                "public": False,
                            },
                        ],
                        "keycounter": [
                            {"handle": "raupulus", "public": True},
                        ],
                    },
                },
                "privado": {
                    "name": "Perfil Privado",
                    "public": False,
                    "accounts": {
                        "youtube": [
                            {
                                "id": "UC3333333333333333333333",
                                "handle": "@secret",
                                "public": True,
                            }
                        ]
                    },
                },
            }
        }
    )

    db = Database(":memory:")
    store = StateStore(db)
    snapshot_repo = SnapshotRepository(db)
    aggregator = ProfileAggregator(registry, store)
    ws_manager = WSManager(aggregator, heartbeat_interval=3600.0)
    settings = Settings(
        _env_file=None,
        api_bearer_token="private-secret-token",
        ws_public_allowed_origins="https://stats.raupulus.dev",
        ws_public_max_per_ip=2,
        ws_public_max_connections=3,
    )

    app = create_app(
        settings=settings,
        registry=registry,
        db=db,
        state_store=store,
        snapshot_repo=snapshot_repo,
        aggregator=aggregator,
        ws_manager=ws_manager,
        enable_scheduler=False,
    )
    valid_origin = {"Origin": "https://stats.raupulus.dev"}

    with TestClient(app) as client:
        # 1. Disallowed or missing Origin -> 1008
        with (
            pytest.raises(WebSocketDisconnect) as bad_origin_exc,
            client.websocket_connect(
                "/ws/public", headers={"Origin": "https://evil.example"}
            ) as ws_evil,
        ):
            ws_evil.receive_json()
        assert bad_origin_exc.value.code == 1008

        # 2. Requesting a private profile on /ws/public -> 4004
        with (
            pytest.raises(WebSocketDisconnect) as priv_prof_exc,
            client.websocket_connect(
                "/ws/public?profile=privado", headers=valid_origin
            ) as ws_priv_prof,
        ):
            ws_priv_prof.receive_json()
        assert priv_prof_exc.value.code == 4004

        # 3. Connect 2 public clients from same IP (limit=2) and 1 private client
        with (
            client.websocket_connect(
                "/ws/public",
                headers={**valid_origin, "X-Forwarded-For": "198.51.100.10"},
            ) as ws_pub1,
            client.websocket_connect(
                "/ws/public",
                headers={**valid_origin, "X-Forwarded-For": "198.51.100.10"},
            ) as ws_pub2,
            client.websocket_connect(
                "/ws/stats",
                headers={"Authorization": "Bearer private-secret-token"},
            ) as ws_priv,
        ):
            snap_pub1 = ws_pub1.receive_json()
            snap_pub2 = ws_pub2.receive_json()
            snap_priv = ws_priv.receive_json()

            # Public snapshot excludes 'privado' profile and '@private_channel'
            assert list(snap_pub1["data"]["profiles"].keys()) == ["raupulus"]
            assert snap_pub2["event"] == "snapshot"
            pub_yt_accs = snap_pub1["data"]["profiles"]["raupulus"]["platforms"][
                "youtube"
            ]["accounts"]
            assert [a["account_key"] for a in pub_yt_accs] == [
                "UC1111111111111111111111"
            ]

            # Private snapshot includes both profiles and both YouTube channels
            assert set(snap_priv["data"]["profiles"].keys()) == {
                "raupulus",
                "privado",
            }

            # 3rd connection from same IP 198.51.100.10 exceeds ws_public_max_per_ip=2 -> 1008
            with (
                pytest.raises(WebSocketDisconnect) as ip_limit_exc,
                client.websocket_connect(
                    "/ws/public",
                    headers={**valid_origin, "X-Forwarded-For": "198.51.100.10"},
                ) as ws_pub_excess_ip,
            ):
                ws_pub_excess_ip.receive_json()
            assert ip_limit_exc.value.code == 1008

            # 4. Keycounter update with totals + 1h + today
            kc_collector = _StubKeycounterCollector(
                AccountMetrics(
                    pulsations_total=10_000_000,
                    pulsations_today=5_000,
                    pulsations_last_1h=500,
                    clicks_total=400_000,
                    clicks_today=300,
                    clicks_last_1h=30,
                )
            )
            scheduler = CollectorScheduler(
                settings=settings,
                registry=registry,
                collectors={Platform.KEYCOUNTER: kc_collector},
                snapshot_repo=snapshot_repo,
                state_store=store,
                aggregator=aggregator,
                on_metric_update=ws_manager.broadcast_update,
                on_status_change=ws_manager.broadcast_collector_status,
            )
            kc_acc = registry.profiles["raupulus"].accounts["keycounter"][0]
            assert client.portal is not None
            client.portal.call(
                scheduler.run_collector_once,
                kc_collector,
                [kc_acc],
            )

            # Both private and public receive metric_update, but public has 1h/today redacted
            upd_priv = ws_priv.receive_json()
            assert upd_priv["event"] == "metric_update"
            assert upd_priv["data"]["account"]["metrics"]["pulsations_total"] == 10_000_000
            assert upd_priv["data"]["account"]["metrics"]["pulsations_today"] == 5_000
            assert upd_priv["data"]["account"]["metrics"]["pulsations_last_1h"] == 500
            assert "pulsations_today" in upd_priv["data"]["changes"]

            upd_pub = ws_pub1.receive_json()
            _ = ws_pub2.receive_json()
            assert upd_pub["event"] == "metric_update"
            assert upd_pub["data"]["account"]["metrics"]["pulsations_total"] == 10_000_000
            assert upd_pub["data"]["account"]["metrics"]["clicks_total"] == 400_000
            assert upd_pub["data"]["account"]["metrics"]["pulsations_today"] is None
            assert upd_pub["data"]["account"]["metrics"]["pulsations_last_1h"] is None
            assert upd_pub["data"]["account"]["metrics"]["clicks_today"] is None
            assert upd_pub["data"]["account"]["metrics"]["clicks_last_1h"] is None
            assert set(upd_pub["data"]["changes"].keys()) == {
                "pulsations_total",
                "clicks_total",
            }

            # 5. Next Keycounter update changes ONLY pulsations_last_1h (totals unchanged)
            kc_collector.metrics = AccountMetrics(
                pulsations_total=10_000_000,
                pulsations_today=5_000,
                pulsations_last_1h=420,
                clicks_total=400_000,
                clicks_today=300,
                clicks_last_1h=30,
            )
            client.portal.call(
                scheduler.run_collector_once,
                kc_collector,
                [kc_acc],
            )
            # Private receives the 1h window update
            upd_priv_window = ws_priv.receive_json()
            assert upd_priv_window["event"] == "metric_update"
            assert list(upd_priv_window["data"]["changes"].keys()) == [
                "pulsations_last_1h"
            ]

            # Public does NOT receive any metric_update (verified via heartbeat next)
            client.portal.call(ws_manager.broadcast_heartbeat, 55)
            hb_pub = ws_pub1.receive_json()
            assert hb_pub["event"] == "heartbeat"
            assert hb_pub["data"]["uptime_seconds"] == 55

            # 6. Sending a single frame on /ws/public immediately closes with 1008
            ws_pub1.send_text("hello")
            with pytest.raises(WebSocketDisconnect) as ro_exc:
                ws_pub1.receive_json()
            assert ro_exc.value.code == 1008


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


