"""Main API v1 router combining health, stats, and WebSocket endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from social_stats.api.routes_health import local_health_router
from social_stats.api.routes_health import router as health_router
from social_stats.api.routes_stats import router as stats_router
from social_stats.api.routes_ws import router as ws_router
from social_stats.api.security import require_private_api_token

api_v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_private_api_token)],
)
api_v1_router.include_router(health_router)
api_v1_router.include_router(stats_router)

__all__ = ["api_v1_router", "local_health_router", "ws_router"]
