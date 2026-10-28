"""Health endpoint GET /api/v1/health."""

from __future__ import annotations

import time
from typing import cast

from fastapi import APIRouter, Request

from social_stats.models.api import HealthResponse
from social_stats.models.enums import CollectorStatus
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.database import Database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Return service uptime, SQLite responsiveness, and collector health summary."""
    db = cast(Database, request.app.state.db)
    aggregator = cast(ProfileAggregator, request.app.state.aggregator)
    start_monotonic = cast(float, request.app.state.start_monotonic)

    db_ok = await db.check_health()
    collectors = aggregator.get_collectors_health()

    has_degraded_collector = any(
        c.status in {CollectorStatus.STALE, CollectorStatus.ERROR}
        for c in collectors.values()
    )
    overall_status = "ok" if (db_ok and not has_degraded_collector) else "degraded"
    uptime_seconds = max(0, int(time.monotonic() - start_monotonic))

    return HealthResponse(
        status=overall_status,
        uptime_seconds=uptime_seconds,
        database_ok=db_ok,
        collectors=collectors,
    )
