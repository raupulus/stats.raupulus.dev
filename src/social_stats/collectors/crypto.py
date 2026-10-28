"""Cryptocurrency spot price collector (BTC, ADA, etc. in USD and EUR) via Binance Public API."""

from __future__ import annotations

import json
from typing import Any

import httpx

from social_stats.collectors.base import (
    DEFAULT_HTTP_TIMEOUT,
    BaseCollector,
    CollectorError,
)
from social_stats.config.profiles import AccountConfig
from social_stats.models.enums import Platform
from social_stats.models.metrics import AccountMetrics

BINANCE_API_BASE_URL = "https://api.binance.com/api/v3"
BINANCE_TICKER_24HR_URL = f"{BINANCE_API_BASE_URL}/ticker/24hr"
BINANCE_TICKER_PRICE_URL = f"{BINANCE_API_BASE_URL}/ticker/price"


def _parse_float(value: Any) -> float | None:
    """Safely convert a string or numeric value from Binance JSON into a float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class CryptoCollector(BaseCollector):
    """
    Collects spot prices and 24h market statistics in USD (USDT) and EUR
    for cryptocurrency assets (e.g. BTC, ADA) using the tokenless Binance Public API.
    """

    platform = Platform.CRYPTO
    default_poll_interval = 60

    async def _fetch_single_pair(
        self, client: httpx.AsyncClient, symbol_pair: str
    ) -> dict[str, Any] | None:
        """Fetch a single trading pair (used as fallback when batch contains an unsupported pair)."""
        resp = await client.get(
            BINANCE_TICKER_24HR_URL,
            params={"symbol": symbol_pair},
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                return data
            return None
        if resp.status_code == 400:
            return None
        raise CollectorError(
            f"Binance ticker/24hr failed for '{symbol_pair}' with HTTP {resp.status_code}",
            status_code=resp.status_code,
        )

    async def _fetch_pairs_batch(
        self, client: httpx.AsyncClient, pairs: list[str]
    ) -> dict[str, dict[str, Any]]:
        """
        Fetch 24hr ticker statistics for all requested trading pairs in a single HTTP call.
        Falls back to per-pair queries if Binance returns HTTP 400 (-1121 Invalid symbol)
        so one unsupported pair never aborts valid pairs like BTCUSDT/BTCEUR.
        """
        if not pairs:
            return {}

        symbols_param = json.dumps(pairs, separators=(",", ":"))
        resp = await client.get(
            BINANCE_TICKER_24HR_URL,
            params={"symbols": symbols_param},
        )

        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, list):
                return {
                    str(item["symbol"]).upper(): item
                    for item in payload
                    if isinstance(item, dict) and "symbol" in item
                }
            return {}

        if resp.status_code == 400:
            results: dict[str, dict[str, Any]] = {}
            for pair in pairs:
                item = await self._fetch_single_pair(client, pair)
                if item is not None and "symbol" in item:
                    results[str(item["symbol"]).upper()] = item
            return results

        raise CollectorError(
            f"Binance ticker/24hr batch failed with HTTP {resp.status_code}",
            status_code=resp.status_code,
        )

    async def _collect_with_client(
        self,
        client: httpx.AsyncClient,
        accounts: list[AccountConfig],
    ) -> dict[str, AccountMetrics]:
        requested_pairs: list[str] = []
        seen_pairs: set[str] = set()
        account_symbols: dict[str, tuple[str, str]] = {}

        for acc in accounts:
            base_symbol = acc.account_key.upper()
            usd_pair = f"{base_symbol}USDT"
            eur_pair = f"{base_symbol}EUR"
            account_symbols[acc.account_key] = (usd_pair, eur_pair)
            for pair in (usd_pair, eur_pair):
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    requested_pairs.append(pair)

        pairs_data = await self._fetch_pairs_batch(client, requested_pairs)

        results: dict[str, AccountMetrics] = {}
        for acc in accounts:
            usd_pair, eur_pair = account_symbols[acc.account_key]
            usd_info = pairs_data.get(usd_pair)
            eur_info = pairs_data.get(eur_pair)

            if usd_info is None and eur_info is None:
                self.record_account_error(
                    acc.account_key,
                    f"Binance returned no market data for '{usd_pair}' or '{eur_pair}'",
                )
                continue

            price_usd = (
                _parse_float(usd_info.get("lastPrice") or usd_info.get("price"))
                if usd_info
                else None
            )
            price_eur = (
                _parse_float(eur_info.get("lastPrice") or eur_info.get("price"))
                if eur_info
                else None
            )

            if price_usd is None and price_eur is None:
                self.record_account_error(
                    acc.account_key,
                    f"Invalid price payload for '{acc.account_key}' from Binance",
                )
                continue

            base_metrics = AccountMetrics(
                price_usd=price_usd,
                price_eur=price_eur,
                price_change_24h_usd=(
                    _parse_float(usd_info.get("priceChange")) if usd_info else None
                ),
                price_change_24h_pct=(
                    _parse_float(usd_info.get("priceChangePercent")) if usd_info else None
                ),
                price_change_24h_eur=(
                    _parse_float(eur_info.get("priceChange")) if eur_info else None
                ),
                price_change_24h_eur_pct=(
                    _parse_float(eur_info.get("priceChangePercent")) if eur_info else None
                ),
                high_24h_usd=(
                    _parse_float(usd_info.get("highPrice")) if usd_info else None
                ),
                low_24h_usd=(
                    _parse_float(usd_info.get("lowPrice")) if usd_info else None
                ),
                high_24h_eur=(
                    _parse_float(eur_info.get("highPrice")) if eur_info else None
                ),
                low_24h_eur=(
                    _parse_float(eur_info.get("lowPrice")) if eur_info else None
                ),
            )
            enriched = await self.enrich_with_snapshots(acc.account_key, base_metrics)
            results[acc.account_key] = enriched

        return results

    async def collect_batch(
        self, accounts: list[AccountConfig]
    ) -> dict[str, AccountMetrics]:
        """Collect USD and EUR spot prices and 24h stats for all configured crypto assets."""
        if not accounts:
            return {}

        if self._external_client is not None:
            return await self._collect_with_client(self._external_client, accounts)

        async with httpx.AsyncClient(timeout=DEFAULT_HTTP_TIMEOUT) as client:
            return await self._collect_with_client(client, accounts)
