"""Unit tests for CryptoCollector (Binance Public API spot prices in USD and EUR)."""

from __future__ import annotations

import httpx
import respx

from social_stats.collectors.crypto import (
    BINANCE_TICKER_24HR_URL,
    CryptoCollector,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.storage.snapshot_repo import SnapshotRepository
from social_stats.storage.state_store import DiffEngine


async def test_crypto_collector_batch_btc_and_ada(
    snapshot_repo: SnapshotRepository,
) -> None:
    """
    Verify that CryptoCollector batches BTC and ADA (both USDT and EUR pairs)
    into a single HTTP request to Binance ticker/24hr, parses spot prices and
    24h stats, and persists price_usd/price_eur into SQLite snapshots.
    """
    accounts = [
        AccountConfig(
            handle="BTC",
            label="Bitcoin (BTC)",
            platform="crypto",
            account_key="btc",
        ),
        AccountConfig(
            handle="ADA",
            label="Cardano (ADA)",
            platform="crypto",
            account_key="ada",
        ),
    ]

    binance_payload = [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "81285.45000000",
            "priceChange": "497.86000000",
            "priceChangePercent": "0.616",
            "highPrice": "81823.00000000",
            "lowPrice": "80397.14000000",
        },
        {
            "symbol": "BTCEUR",
            "lastPrice": "72791.52000000",
            "priceChange": "335.61000000",
            "priceChangePercent": "0.463",
            "highPrice": "73471.72000000",
            "lowPrice": "72050.00000000",
        },
        {
            "symbol": "ADAUSDT",
            "lastPrice": "0.48500000",
            "priceChange": "0.01500000",
            "priceChangePercent": "3.191",
            "highPrice": "0.49500000",
            "lowPrice": "0.46800000",
        },
        {
            "symbol": "ADAEUR",
            "lastPrice": "0.44700000",
            "priceChange": "0.01200000",
            "priceChangePercent": "2.758",
            "highPrice": "0.45500000",
            "lowPrice": "0.43100000",
        },
    ]

    with respx.mock(assert_all_called=True) as respx_mock:
        route = respx_mock.get(BINANCE_TICKER_24HR_URL).mock(
            return_value=httpx.Response(200, json=binance_payload)
        )

        async with httpx.AsyncClient() as client:
            collector = CryptoCollector(
                snapshot_repo=snapshot_repo,
                http_client=client,
            )
            collector.reset_cycle_tracking(now_ts=1730000000)
            results = await collector.collect_batch(accounts)

        assert route.call_count == 1
        req_url = str(route.calls[0].request.url)
        assert "BTCUSDT" in req_url
        assert "BTCEUR" in req_url
        assert "ADAUSDT" in req_url
        assert "ADAEUR" in req_url

    assert set(results.keys()) == {"btc", "ada"}

    btc = results["btc"]
    assert btc.price_usd == 81285.45
    assert btc.price_eur == 72791.52
    assert btc.price_change_24h_usd == 497.86
    assert btc.price_change_24h_pct == 0.616
    assert btc.price_change_24h_eur == 335.61
    assert btc.price_change_24h_eur_pct == 0.463
    assert btc.high_24h_usd == 81823.0
    assert btc.low_24h_usd == 80397.14
    assert btc.high_24h_eur == 73471.72
    assert btc.low_24h_eur == 72050.0

    ada = results["ada"]
    assert ada.price_usd == 0.485
    assert ada.price_eur == 0.447
    assert ada.price_change_24h_pct == 3.191
    assert ada.price_change_24h_eur_pct == 2.758

    # Verify snapshot history persisted price_usd and price_eur
    history = await snapshot_repo.get_history(
        Platform.CRYPTO,
        "btc",
        window_seconds=3600,
        now_ts=1730000000,
    )
    assert len(history) == 1
    assert history[0].price_usd == 81285.45
    assert history[0].price_eur == 72791.52

    # Verify DiffEngine detects price changes accurately
    updated_btc = btc.model_copy(update={"price_usd": 81500.0, "price_eur": 73000.0})
    diff = DiffEngine.compute_diff(btc, updated_btc)
    assert diff.has_changes is True
    assert diff.changes["price_usd"].previous == 81285.45
    assert diff.changes["price_usd"].current == 81500.0
    assert diff.changes["price_usd"].delta == 214.55
    assert diff.changes["price_eur"].delta == 208.48


async def test_crypto_collector_fallback_on_invalid_symbol_in_batch() -> None:
    """
    Verify that if Binance returns HTTP 400 (-1121 Invalid symbol) on the batch request
    because one configured coin lacks an EUR pair or is invalid, CryptoCollector falls back
    to individual pair queries and still succeeds for BTC while recording an error for the
    invalid asset.
    """
    accounts = [
        AccountConfig(
            handle="BTC",
            label="Bitcoin",
            platform="crypto",
            account_key="btc",
        ),
        AccountConfig(
            handle="FAKECOIN",
            label="Fake Coin",
            platform="crypto",
            account_key="fakecoin",
        ),
    ]

    def _binance_handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if "symbols" in params:
            return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
        sym = params.get("symbol", "")
        if sym == "BTCUSDT":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "lastPrice": "82000.00",
                    "priceChange": "1000.00",
                    "priceChangePercent": "1.23",
                    "highPrice": "82500.00",
                    "lowPrice": "80500.00",
                },
            )
        if sym == "BTCEUR":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCEUR",
                    "lastPrice": "73500.00",
                    "priceChange": "900.00",
                    "priceChangePercent": "1.24",
                    "highPrice": "74000.00",
                    "lowPrice": "72200.00",
                },
            )
        return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

    with respx.mock(assert_all_called=True) as respx_mock:
        respx_mock.get(BINANCE_TICKER_24HR_URL).mock(side_effect=_binance_handler)

        async with httpx.AsyncClient() as client:
            collector = CryptoCollector(http_client=client)
            collector.reset_cycle_tracking()
            results = await collector.collect_batch(accounts)

    assert "btc" in results
    assert results["btc"].price_usd == 82000.0
    assert results["btc"].price_eur == 73500.0
    assert "fakecoin" not in results
    assert "fakecoin" in collector.last_errors
