"""Enumerations for platforms, collector statuses, and WebSocket event types."""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    """Supported social media, market data, and activity telemetry platforms."""

    YOUTUBE = "youtube"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    BLUESKY = "bluesky"
    MASTODON = "mastodon"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    CRYPTO = "crypto"
    KEYCOUNTER = "keycounter"


class CollectorStatus(StrEnum):
    """Health status of an account or platform collector."""

    HEALTHY = "healthy"
    STALE = "stale"
    ERROR = "error"
    DISABLED = "disabled"


class WSEventType(StrEnum):
    """Types of events pushed over the Read-Only WebSocket stream."""

    SNAPSHOT = "snapshot"
    METRIC_UPDATE = "metric_update"
    COLLECTOR_STATUS = "collector_status"
    HEARTBEAT = "heartbeat"
