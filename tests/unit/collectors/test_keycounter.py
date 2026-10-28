"""Unit tests for KeycounterCollector (api.raupulus.dev API v2)."""

from __future__ import annotations

import httpx

from social_stats.collectors.keycounter import (
    DEFAULT_KEYCOUNTER_API_URL,
    KeycounterCollector,
)
from social_stats.config.profiles import AccountConfig
from social_stats.config.settings import Settings
from social_stats.models.enums import Platform
from social_stats.storage.snapshot_repo import SnapshotRepository

SAMPLE_KEYCOUNTER_200_PAYLOAD = {
    "success": True,
    "message": "Operación exitosa",
    "data": {
        "user_id": 1,
        "lifetime_pulsations": 12845620,
        "today_pulsations": 15420,
        "last_hour_pulsations": 1850,
        "lifetime_clicks": 450120,
        "today_clicks": 1200,
        "last_hour_clicks": 150,
        "today_from": "2026-10-28T00:00:00.000000Z",
        "last_hour_from": "2026-10-28T21:00:00.000000Z",
        "generated_at": "2026-10-28T22:00:00.000000Z",
    },
}


async def test_keycounter_collector_success_and_snapshot_persistence(
    snapshot_repo: SnapshotRepository,
) -> None:
    """
    Verify KeycounterCollector sends Bearer token & Accept: application/json headers,
    parses pulsations and clicks (lifetime, today, last_hour), and records snapshots.
    """
    captured_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == DEFAULT_KEYCOUNTER_API_URL
        captured_headers["Authorization"] = request.headers.get("Authorization", "")
        captured_headers["Accept"] = request.headers.get("Accept", "")
        return httpx.Response(200, json=SAMPLE_KEYCOUNTER_200_PAYLOAD)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        collector = KeycounterCollector(
            api_token="dummy_bearer_token_for_unit_test",
            snapshot_repo=snapshot_repo,
            http_client=client,
        )
        collector.reset_cycle_tracking(now_ts=1_730_000_000)

        acc = AccountConfig(
            handle="raupulus",
            label="Keycounter Principal",
            platform="keycounter",
            account_key="raupulus",
        )
        results = await collector.collect_batch([acc])

    assert captured_headers["Authorization"] == "Bearer dummy_bearer_token_for_unit_test"
    assert captured_headers["Accept"] == "application/json"

    assert "raupulus" in results
    m = results["raupulus"]
    assert m.pulsations_total == 12_845_620
    assert m.pulsations_today == 15_420
    assert m.pulsations_last_1h == 1_850
    assert m.clicks_total == 450_120
    assert m.clicks_today == 1_200
    assert m.clicks_last_1h == 150
    assert m.window_1h_complete is True
    assert m.window_24h_complete is True
    assert "raupulus" in collector.enriched_accounts

    history = await snapshot_repo.get_history(
        Platform.KEYCOUNTER,
        "raupulus",
        window_seconds=3600,
        now_ts=1_730_000_000,
    )
    assert len(history) == 1
    assert history[0].pulsations_total == 12_845_620
    assert history[0].clicks_total == 450_120


async def test_keycounter_collector_missing_token_marks_disabled() -> None:
    """Verify accounts without a configured token are marked disabled without HTTP errors."""
    collector = KeycounterCollector(
        settings=Settings(_env_file=None, keycounter_api_token=""),
    )
    acc = AccountConfig(
        handle="raupulus",
        credentials_ref="MISSING_REF",
        platform="keycounter",
        account_key="raupulus",
    )
    results = await collector.collect_batch([acc])
    assert results == {}
    assert "raupulus" in collector.disabled_accounts


async def test_keycounter_collector_404_and_error_handling() -> None:
    """
    Verify KeycounterCollector records per-account error when the upstream API returns
    HTTP 404 {"success": false, "message": "API V2 - Endpoint no encontrado"} or success=false.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if "notfound" in str(request.url):
            return httpx.Response(
                404,
                json={"success": False, "message": "API V2 - Endpoint no encontrado"},
            )
        return httpx.Response(
            200,
            json={"success": False, "message": "Token inválido"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        collector = KeycounterCollector(
            api_token="dummy_token",
            http_client=client,
        )
        acc_404 = AccountConfig(
            handle="acc404",
            instance="https://api.raupulus.dev/api/v2/notfound",
            platform="keycounter",
            account_key="acc404",
        )
        acc_false = AccountConfig(
            handle="accfalse",
            instance="https://api.raupulus.dev/api/v2/keycounter/stats",
            platform="keycounter",
            account_key="accfalse",
        )
        results = await collector.collect_batch([acc_404, acc_false])

    assert results == {}
    assert "HTTP 404" in collector.last_errors["acc404"]
    assert "API V2 - Endpoint no encontrado" in collector.last_errors["acc404"]
    assert "Token inválido" in collector.last_errors["accfalse"]
