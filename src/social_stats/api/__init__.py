"""API package exposing Read-Only REST v1 and WebSocket routers."""

from social_stats.api.router import api_v1_router, ws_router

__all__ = ["api_v1_router", "ws_router"]
