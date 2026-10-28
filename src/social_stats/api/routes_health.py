"""Health endpoints: private GET /api/v1/health and localhost-only GET /healthz."""

from __future__ import annotations

import time
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from social_stats.api.security import is_local_loopback_request
from social_stats.models.api import HealthResponse
from social_stats.models.enums import CollectorStatus
from social_stats.services.aggregator import ProfileAggregator
from social_stats.storage.database import Database

router = APIRouter(tags=["health"])
local_health_router = APIRouter(tags=["health"])


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


@local_health_router.get("/healthz", include_in_schema=False)
async def get_local_docker_healthz(request: Request) -> JSONResponse:
    """
    Minimal healthcheck endpoint restricted strictly to loopback (127.0.0.1 / ::1 / localhost)
    without reverse-proxy forwarding headers, intended exclusively for Docker HEALTHCHECK.
    """
    if not is_local_loopback_request(request):
        return JSONResponse(
            status_code=403,
            content={
                "error": "forbidden",
                "message": "Endpoint restringido exclusivamente a localhost.",
            },
        )

    db = cast(Database, request.app.state.db)
    db_ok = await db.check_health()
    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "error",
            "database_ok": db_ok,
        },
    )
