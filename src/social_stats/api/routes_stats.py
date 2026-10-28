"""REST Read-Only endpoints for profiles catalog, global/profile stats, and history."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from social_stats.config.profiles import ProfilesRegistry
from social_stats.models.api import (
    AccountHistorySeries,
    CryptoPricesResponse,
    GlobalStatsResponse,
    ProfileHistoryResponse,
    ProfilesCatalogResponse,
)
from social_stats.models.enums import Platform
from social_stats.models.metrics import ProfileStats
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.snapshot_repo import SnapshotRepository

router = APIRouter(tags=["stats"])

WINDOW_TO_SECONDS: dict[str, int] = {
    "1h": 3600,
    "24h": 86400,
    "7d": 7 * 86400,
    "30d": 30 * 86400,
}


def _profile_not_found_response(
    profile_id: str, registry: ProfilesRegistry
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "profile_not_found",
            "message": f"El perfil '{profile_id}' no está definido en profiles.yaml",
            "available_profiles": list(registry.profiles.keys()),
        },
    )


def _platform_not_found_response(platform: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "platform_not_found",
            "message": f"La plataforma '{platform}' no está soportada",
            "available_platforms": [p.value for p in Platform],
        },
    )


def _parse_platform_filter(platform: str | None) -> Platform | None:
    if platform is None:
        return None
    return Platform(platform.strip().lower())


@router.get("/profiles", response_model=ProfilesCatalogResponse)
async def list_profiles(request: Request) -> ProfilesCatalogResponse:
    """Return catalog of all configured profiles and their active platforms."""
    aggregator = cast(ProfileAggregator, request.app.state.aggregator)
    return aggregator.get_profiles_catalog()


@router.get("/crypto", response_model=CryptoPricesResponse)
async def get_crypto_prices(
    request: Request,
    symbol: str | None = Query(
        default=None, description="Optional crypto ticker filter (e.g. BTC, ADA)"
    ),
) -> CryptoPricesResponse | JSONResponse:
    """Return spot prices and 24h market stats in USD and EUR for configured crypto assets."""
    aggregator = cast(ProfileAggregator, request.app.state.aggregator)
    response = aggregator.get_crypto_prices(symbol_filter=symbol)
    if symbol is not None and not response.assets:
        all_crypto = aggregator.get_crypto_prices()
        return JSONResponse(
            status_code=404,
            content={
                "error": "crypto_symbol_not_found",
                "message": f"El activo cripto '{symbol}' no está configurado",
                "available_symbols": list(all_crypto.assets.keys()),
            },
        )
    return response


@router.get("/stats", response_model=GlobalStatsResponse)
async def get_global_stats(
    request: Request,
    profile: str | None = Query(default=None, description="Optional profile_id filter"),
    platform: str | None = Query(default=None, description="Optional platform filter"),
) -> GlobalStatsResponse | JSONResponse:
    """Return global statistics across all profiles (or filtered by profile/platform)."""
    registry = cast(ProfilesRegistry, request.app.state.registry)
    aggregator = cast(ProfileAggregator, request.app.state.aggregator)

    if profile is not None and registry.get_profile(profile) is None:
        return _profile_not_found_response(profile, registry)

    try:
        parsed_platform = _parse_platform_filter(platform)
    except ValueError:
        return _platform_not_found_response(platform or "")

    return aggregator.get_global_stats(
        profile_filter=profile,
        platform_filter=parsed_platform,
    )


@router.get("/profiles/{profile_id}/stats", response_model=ProfileStats)
async def get_profile_stats(
    profile_id: str,
    request: Request,
    platform: str | None = Query(default=None, description="Optional platform filter"),
) -> ProfileStats | JSONResponse:
    """Return aggregated and per-account statistics for a specific profile."""
    registry = cast(ProfilesRegistry, request.app.state.registry)
    aggregator = cast(ProfileAggregator, request.app.state.aggregator)

    if registry.get_profile(profile_id) is None:
        return _profile_not_found_response(profile_id, registry)

    try:
        parsed_platform = _parse_platform_filter(platform)
    except ValueError:
        return _platform_not_found_response(platform or "")

    pstats = aggregator.get_profile_stats(
        profile_id,
        platform_filter=parsed_platform,
    )
    if pstats is None:
        return _profile_not_found_response(profile_id, registry)
    return pstats


@router.get("/profiles/{profile_id}/history", response_model=ProfileHistoryResponse)
async def get_profile_history(
    profile_id: str,
    request: Request,
    platform: str | None = Query(default=None, description="Optional platform filter"),
    account_key: str | None = Query(default=None, description="Optional account_key filter"),
    window: str = Query(default="24h", description="Time window: 1h, 24h, 7d, 30d"),
) -> ProfileHistoryResponse | JSONResponse:
    """Return historical time-series snapshots from SQLite for a profile."""
    registry = cast(ProfilesRegistry, request.app.state.registry)
    snapshot_repo = cast(SnapshotRepository, request.app.state.snapshot_repo)

    pconfig = registry.get_profile(profile_id)
    if pconfig is None:
        return _profile_not_found_response(profile_id, registry)

    try:
        parsed_platform = _parse_platform_filter(platform)
    except ValueError:
        return _platform_not_found_response(platform or "")

    clean_window = window.strip().lower()
    if clean_window not in WINDOW_TO_SECONDS:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_window",
                "message": f"Ventana '{window}' inválida. Valores permitidos: 1h, 24h, 7d, 30d",
                "allowed_windows": list(WINDOW_TO_SECONDS.keys()),
            },
        )

    window_seconds = WINDOW_TO_SECONDS[clean_window]
    series: list[AccountHistorySeries] = []

    for platform_str, acc_list in pconfig.accounts.items():
        plat = Platform(platform_str)
        if parsed_platform is not None and plat != parsed_platform:
            continue
        for acc in acc_list:
            if not acc.enabled:
                continue
            if account_key is not None and acc.account_key != account_key:
                continue
            points = await snapshot_repo.get_history(
                plat,
                acc.account_key,
                window_seconds=window_seconds,
            )
            series.append(
                AccountHistorySeries(
                    platform=plat,
                    account_key=acc.account_key,
                    label=acc.label,
                    points=points,
                )
            )

    return ProfileHistoryResponse(
        profile_id=profile_id,
        window=clean_window,
        generated_at=datetime.now(UTC),
        series=series,
    )
