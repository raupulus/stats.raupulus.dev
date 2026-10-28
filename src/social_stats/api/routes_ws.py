"""Read-Only WebSocket endpoints: public (/ws/public) and private (/ws/stats, /ws/profiles/{profile_id})."""

from __future__ import annotations

import time
from collections import deque
from typing import cast

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from social_stats.api.security import (
    extract_client_ip,
    extract_ws_bearer_token,
    is_allowed_public_ws_origin,
    verify_bearer_token,
)
from social_stats.config.profiles import ProfilesRegistry
from social_stats.config.settings import Settings
from social_stats.models.enums import Platform
from social_stats.services.ws_manager import WSManager

router = APIRouter(tags=["websockets"])

WS_CODE_NOT_FOUND = 4004
WS_CODE_POLICY_VIOLATION = 1008
MAX_INCOMING_MESSAGES_PER_MINUTE = 10
FLOOD_WINDOW_SECONDS = 60.0


async def _handle_private_ws_session(
    websocket: WebSocket,
    *,
    profile_id: str | None,
    platform_raw: str | None,
) -> None:
    """
    Authenticate with API_BEARER_TOKEN, validate subscription scope, send full snapshot,
    and run passive Read-Only loop (flooding >10 msg/min closes with 1008).
    """
    settings = cast(Settings, websocket.app.state.settings)
    registry = cast(ProfilesRegistry, websocket.app.state.registry)
    ws_manager = cast(WSManager, websocket.app.state.ws_manager)

    token, subprotocol = extract_ws_bearer_token(websocket)
    if not verify_bearer_token(token, settings.api_bearer_token):
        await websocket.accept()
        await websocket.close(
            code=WS_CODE_POLICY_VIOLATION,
            reason="Policy Violation: Unauthorized",
        )
        return

    if profile_id is not None and registry.get_profile(profile_id) is None:
        await websocket.accept(subprotocol=subprotocol)
        await websocket.close(
            code=WS_CODE_NOT_FOUND,
            reason=f"Profile '{profile_id}' not found",
        )
        return

    parsed_platform: Platform | None = None
    if platform_raw is not None:
        try:
            parsed_platform = Platform(platform_raw.strip().lower())
        except ValueError:
            await websocket.accept(subprotocol=subprotocol)
            await websocket.close(
                code=WS_CODE_NOT_FOUND,
                reason=f"Platform '{platform_raw}' not supported",
            )
            return

    await ws_manager.connect(
        websocket,
        profile_id=profile_id,
        platform=parsed_platform,
        is_public=False,
        subprotocol=subprotocol,
    )

    msg_timestamps: deque[float] = deque()
    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                break

            if "text" in message or "bytes" in message:
                now_mono = time.monotonic()
                while (
                    msg_timestamps
                    and (now_mono - msg_timestamps[0]) > FLOOD_WINDOW_SECONDS
                ):
                    msg_timestamps.popleft()
                msg_timestamps.append(now_mono)

                if len(msg_timestamps) > MAX_INCOMING_MESSAGES_PER_MINUTE:
                    await websocket.close(
                        code=WS_CODE_POLICY_VIOLATION,
                        reason="Policy Violation: Read-Only stream",
                    )
                    break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


async def _handle_public_ws_session(
    websocket: WebSocket,
    *,
    profile_id: str | None,
    platform_raw: str | None,
) -> None:
    """
    Public Read-Only WebSocket stream (/ws/public) with Origin verification,
    per-IP and global connection limits, public-only profile/account filtering,
    Keycounter lifetime-only redaction, and immediate 1008 closure on any incoming frame.
    """
    settings = cast(Settings, websocket.app.state.settings)
    registry = cast(ProfilesRegistry, websocket.app.state.registry)
    ws_manager = cast(WSManager, websocket.app.state.ws_manager)

    if not is_allowed_public_ws_origin(websocket, settings.ws_public_origins_list):
        await websocket.accept()
        await websocket.close(
            code=WS_CODE_POLICY_VIOLATION,
            reason="Policy Violation: Origin not allowed",
        )
        return

    client_ip = extract_client_ip(websocket)
    allowed, reason = ws_manager.can_accept_public(
        client_ip,
        max_connections=settings.ws_public_max_connections,
        max_per_ip=settings.ws_public_max_per_ip,
    )
    if not allowed:
        await websocket.accept()
        await websocket.close(
            code=WS_CODE_POLICY_VIOLATION,
            reason=reason,
        )
        return

    if profile_id is not None:
        pconfig = registry.get_profile(profile_id)
        if pconfig is None or not pconfig.enable or not pconfig.public:
            await websocket.accept()
            await websocket.close(
                code=WS_CODE_NOT_FOUND,
                reason=f"Profile '{profile_id}' not found",
            )
            return

    parsed_platform: Platform | None = None
    if platform_raw is not None:
        try:
            parsed_platform = Platform(platform_raw.strip().lower())
        except ValueError:
            await websocket.accept()
            await websocket.close(
                code=WS_CODE_NOT_FOUND,
                reason=f"Platform '{platform_raw}' not supported",
            )
            return

    await ws_manager.connect(
        websocket,
        profile_id=profile_id,
        platform=parsed_platform,
        is_public=True,
        client_ip=client_ip,
    )

    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                break

            if "text" in message or "bytes" in message:
                await websocket.close(
                    code=WS_CODE_POLICY_VIOLATION,
                    reason="Policy Violation: Public stream is strictly Read-Only",
                )
                break
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket)


@router.websocket("/ws/public")
async def ws_public_stats(
    websocket: WebSocket,
    profile: str | None = Query(default=None),
    platform: str | None = Query(default=None),
) -> None:
    """Public WebSocket stream exposing only public profiles/accounts and Keycounter totals."""
    await _handle_public_ws_session(
        websocket,
        profile_id=profile,
        platform_raw=platform,
    )


@router.websocket("/ws/stats")
async def ws_global_or_filtered_stats(
    websocket: WebSocket,
    profile: str | None = Query(default=None),
    platform: str | None = Query(default=None),
) -> None:
    """Private authenticated WebSocket stream for global stats or filtered by ?profile={id}&platform={p}."""
    await _handle_private_ws_session(
        websocket,
        profile_id=profile,
        platform_raw=platform,
    )


@router.websocket("/ws/profiles/{profile_id}")
async def ws_profile_stats(
    websocket: WebSocket,
    profile_id: str,
    platform: str | None = Query(default=None),
) -> None:
    """Private authenticated WebSocket stream scoped to a specific profile_id."""
    await _handle_private_ws_session(
        websocket,
        profile_id=profile_id,
        platform_raw=platform,
    )
