"""Pydantic v2 domain models for account metrics, state, and profile aggregations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from social_stats.models.enums import CollectorStatus, Platform


class LatestPostMetrics(BaseModel):
    """Metrics for the most recent original post or video of an account."""

    post_id: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None


class AccountMetrics(BaseModel):
    """Normalized metrics for a single social media account, channel, or crypto asset."""

    followers_total: int | None = None
    followers_last_24h: int | None = None
    posts_total: int | None = None
    views_total: int | None = None
    views_last_24h: int | None = None
    views_last_1h: int | None = None
    window_1h_complete: bool = False
    window_24h_complete: bool = False
    latest_post: LatestPostMetrics | None = None
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


class AccountState(BaseModel):
    """Full state of an individual account including health metadata and metrics."""

    platform: Platform
    account_key: str
    handle: str | None = None
    label: str | None = None
    status: CollectorStatus
    last_updated_at: datetime | None = None
    last_attempt_at: datetime | None = None
    error_message: str | None = None
    metrics: AccountMetrics = Field(default_factory=AccountMetrics)


class PlatformSummary(BaseModel):
    """Aggregated summary of all accounts for a platform within a profile."""

    platform: Platform
    accounts_count: int
    status: CollectorStatus
    followers_total: int = 0
    followers_last_24h: int | None = None
    posts_total: int = 0
    views_total: int | None = None
    views_last_24h: int | None = None
    views_last_1h: int | None = None
    accounts: list[AccountState] = Field(default_factory=list)


class ProfileStats(BaseModel):
    """Aggregated statistics across all configured platforms for a single profile."""

    profile_id: str
    name: str
    description: str | None = None
    updated_at: datetime
    platforms: dict[Platform, PlatformSummary] = Field(default_factory=dict)
