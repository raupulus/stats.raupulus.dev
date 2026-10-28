"""Pydantic v2 schemas for REST API responses and WebSocket event envelopes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from social_stats.models.enums import CollectorStatus, Platform, WSEventType
from social_stats.models.metrics import AccountState, PlatformSummary, ProfileStats


class GlobalStatsResponse(BaseModel):
    """Response schema for GET /api/v1/stats."""

    generated_at: datetime
    profiles: dict[str, ProfileStats] = Field(default_factory=dict)


class ProfileCatalogItem(BaseModel):
    """Summary metadata for a single profile in GET /api/v1/profiles."""

    profile_id: str
    name: str
    description: str | None = None
    platforms: list[Platform] = Field(default_factory=list)
    accounts_count: int = 0


class ProfilesCatalogResponse(BaseModel):
    """Response schema for GET /api/v1/profiles."""

    generated_at: datetime
    profiles: list[ProfileCatalogItem] = Field(default_factory=list)


class HistoryPoint(BaseModel):
    """Single historical snapshot point in a time series."""

    timestamp: datetime
    followers_total: int | None = None
    posts_total: int | None = None
    views_total: int | None = None
    latest_post_views: int | None = None
    price_usd: float | None = None
    price_eur: float | None = None


class CryptoAssetPrice(BaseModel):
    """Current spot price and 24h statistics for a cryptocurrency asset in USD and EUR."""

    symbol: str
    account_key: str
    label: str | None = None
    status: CollectorStatus
    last_updated_at: datetime | None = None
    price_usd: float | None = None
    price_eur: float | None = None
    price_change_24h_usd: float | None = None
    price_change_24h_pct: float | None = None
    price_change_24h_eur: float | None = None
    price_change_24h_eur_pct: float | None = None
    high_24h_usd: float | None = None
    low_24h_usd: float | None = None
    high_24h_eur: float | None = None
    low_24h_eur: float | None = None


class CryptoPricesResponse(BaseModel):
    """Response schema for GET /api/v1/crypto."""

    generated_at: datetime
    assets: dict[str, CryptoAssetPrice] = Field(default_factory=dict)


class AccountHistorySeries(BaseModel):
    """Time series of historical points for a specific account."""

    platform: Platform
    account_key: str
    label: str | None = None
    points: list[HistoryPoint] = Field(default_factory=list)


class ProfileHistoryResponse(BaseModel):
    """Response schema for GET /api/v1/profiles/{profile_id}/history."""

    profile_id: str
    window: str
    generated_at: datetime
    series: list[AccountHistorySeries] = Field(default_factory=list)


class CollectorHealthSummary(BaseModel):
    """Health summary for a single platform collector."""

    platform: Platform
    status: CollectorStatus
    accounts_total: int = 0
    accounts_healthy: int = 0
    accounts_stale: int = 0
    accounts_error: int = 0
    last_success_at: datetime | None = None


class HealthResponse(BaseModel):
    """Response schema for GET /api/v1/health."""

    status: str
    uptime_seconds: int
    database_ok: bool
    collectors: dict[Platform, CollectorHealthSummary] = Field(default_factory=dict)


class WSScope(BaseModel):
    """Scope metadata for a WebSocket event."""

    profile_id: str | None = None
    platform: Platform | None = None


class MetricChange(BaseModel):
    """Represents a numeric diff for a metric field."""

    previous: int | float | None
    current: int | float
    delta: int | float


class MetricUpdateData(BaseModel):
    """Payload for a WebSocket metric_update event."""

    profile_id: str
    platform: Platform
    account_key: str
    label: str | None = None
    is_new_latest_post: bool = False
    changes: dict[str, MetricChange] = Field(default_factory=dict)
    account: AccountState
    platform_summary: PlatformSummary


class CollectorStatusData(BaseModel):
    """Payload for a WebSocket collector_status change event."""

    profile_id: str
    platform: Platform
    account_key: str
    previous_status: CollectorStatus
    current_status: CollectorStatus
    last_updated_at: datetime | None = None
    error_message: str | None = None


class HeartbeatData(BaseModel):
    """Payload for a WebSocket heartbeat event."""

    uptime_seconds: int


class WSEventEnvelope(BaseModel):
    """Uniform envelope for all server-to-client WebSocket events."""

    event: WSEventType
    timestamp: datetime
    scope: WSScope
    data: (
        dict[str, Any]
        | ProfileStats
        | MetricUpdateData
        | CollectorStatusData
        | HeartbeatData
    )
