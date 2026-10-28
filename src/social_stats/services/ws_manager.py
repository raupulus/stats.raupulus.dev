"""WebSocket connection manager supporting global and per-profile Read-Only streams."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

from social_stats.models.api import (
    CollectorStatusData,
    HeartbeatData,
    MetricUpdateData,
    WSEventEnvelope,
    WSScope,
)
from social_stats.models.enums import Platform, WSEventType
from social_stats.services.aggregator import ProfileAggregator

HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


@dataclass(eq=False)
class WSSubscription:
    """Represents a connected Read-Only WebSocket client and its filter scope."""

    websocket: WebSocket
    profile_id: str | None = None
    platform: Platform | None = None


class WSManager:
    """Manages active WebSocket subscriptions, targeted broadcasts, and heartbeats."""

    def __init__(
        self,
        aggregator: ProfileAggregator,
        *,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
        send_timeout: float = DEFAULT_SEND_TIMEOUT_SECONDS,
    ) -> None:
        self.aggregator = aggregator
        self.heartbeat_interval = heartbeat_interval
        self.send_timeout = send_timeout
        self._subscriptions: set[WSSubscription] = set()
        self._ws_to_sub: dict[WebSocket, WSSubscription] = {}
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def active_connections_count(self) -> int:
        """Return number of currently registered WebSocket clients."""
        return len(self._subscriptions)

    async def connect(
        self,
        websocket: WebSocket,
        *,
        profile_id: str | None = None,
        platform: Platform | None = None,
    ) -> WSSubscription:
        """Accept connection, register subscription, and send initial snapshot event."""
        await websocket.accept()
        sub = WSSubscription(
            websocket=websocket,
            profile_id=profile_id,
            platform=platform,
        )
        self._subscriptions.add(sub)
        self._ws_to_sub[websocket] = sub
        await self.send_snapshot(sub)
        return sub

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket client from active subscriptions."""
        sub = self._ws_to_sub.pop(websocket, None)
        if sub is not None:
            self._subscriptions.discard(sub)

    async def _safe_send(
        self, sub: WSSubscription, payload: dict[str, Any]
    ) -> bool:
        """Send JSON payload to a subscriber with timeout; disconnect and return False on error."""
        try:
            await asyncio.wait_for(
                sub.websocket.send_json(payload),
                timeout=self.send_timeout,
            )
            return True
        except Exception:
            self.disconnect(sub.websocket)
            return False

    async def send_snapshot(
        self,
        sub: WSSubscription,
        *,
        now: datetime | None = None,
    ) -> None:
        """Send initial snapshot event tailored to the subscriber's scope."""
        ts = now if now is not None else datetime.now(UTC)
        if sub.profile_id is not None:
            pstats = self.aggregator.get_profile_stats(
                sub.profile_id,
                platform_filter=sub.platform,
                now=ts,
            )
            data: Any = pstats if pstats is not None else {}
        else:
            gstats = self.aggregator.get_global_stats(
                platform_filter=sub.platform,
                now=ts,
            )
            data = {
                "profiles": {
                    pid: prof.model_dump(mode="json")
                    for pid, prof in gstats.profiles.items()
                }
            }

        envelope = WSEventEnvelope(
            event=WSEventType.SNAPSHOT,
            timestamp=ts,
            scope=WSScope(profile_id=sub.profile_id, platform=sub.platform),
            data=data,
        )
        await self._safe_send(sub, envelope.model_dump(mode="json"))

    async def broadcast_update(
        self,
        update_data: MetricUpdateData,
        *,
        now: datetime | None = None,
    ) -> None:
        """Broadcast a metric_update event to global subscribers and matching profile subscribers."""
        if not self._subscriptions:
            return

        ts = now if now is not None else datetime.now(UTC)
        envelope = WSEventEnvelope(
            event=WSEventType.METRIC_UPDATE,
            timestamp=ts,
            scope=WSScope(
                profile_id=update_data.profile_id,
                platform=update_data.platform,
            ),
            data=update_data,
        )
        payload = envelope.model_dump(mode="json")

        targets = [
            sub
            for sub in list(self._subscriptions)
            if (sub.profile_id is None or sub.profile_id == update_data.profile_id)
            and (sub.platform is None or sub.platform == update_data.platform)
        ]
        if targets:
            await asyncio.gather(
                *(self._safe_send(sub, payload) for sub in targets),
                return_exceptions=True,
            )

    async def broadcast_collector_status(
        self,
        status_data: CollectorStatusData,
        *,
        now: datetime | None = None,
    ) -> None:
        """Broadcast a collector_status event to matching subscribers."""
        if not self._subscriptions:
            return

        ts = now if now is not None else datetime.now(UTC)
        envelope = WSEventEnvelope(
            event=WSEventType.COLLECTOR_STATUS,
            timestamp=ts,
            scope=WSScope(
                profile_id=status_data.profile_id,
                platform=status_data.platform,
            ),
            data=status_data,
        )
        payload = envelope.model_dump(mode="json")

        targets = [
            sub
            for sub in list(self._subscriptions)
            if (sub.profile_id is None or sub.profile_id == status_data.profile_id)
            and (sub.platform is None or sub.platform == status_data.platform)
        ]
        if targets:
            await asyncio.gather(
                *(self._safe_send(sub, payload) for sub in targets),
                return_exceptions=True,
            )

    async def broadcast_heartbeat(
        self,
        uptime_seconds: int,
        *,
        now: datetime | None = None,
    ) -> None:
        """Send keep-alive heartbeat event to all active subscribers."""
        if not self._subscriptions:
            return

        ts = now if now is not None else datetime.now(UTC)
        coros = []
        for sub in list(self._subscriptions):
            envelope = WSEventEnvelope(
                event=WSEventType.HEARTBEAT,
                timestamp=ts,
                scope=WSScope(profile_id=sub.profile_id, platform=sub.platform),
                data=HeartbeatData(uptime_seconds=uptime_seconds),
            )
            coros.append(self._safe_send(sub, envelope.model_dump(mode="json")))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _heartbeat_loop(self, get_uptime: Callable[[], int]) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.heartbeat_interval
                )
            except TimeoutError:
                await self.broadcast_heartbeat(get_uptime())

    def start_heartbeat(self, get_uptime: Callable[[], int]) -> None:
        """Start periodic 30s heartbeat background task."""
        if self._heartbeat_task is not None:
            return
        self._stop_event.clear()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(get_uptime),
            name="ws-heartbeat",
        )

    async def stop_heartbeat(self) -> None:
        """Stop periodic heartbeat background task."""
        self._stop_event.set()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
