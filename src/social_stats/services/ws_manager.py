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
from social_stats.models.enums import CollectorStatus, Platform, WSEventType
from social_stats.services.aggregator import (
    KEYCOUNTER_PRIVATE_ONLY_FIELDS,
    ProfileAggregator,
    sanitize_account_state_for_public,
)

HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


@dataclass(eq=False)
class WSSubscription:
    """Represents a connected Read-Only WebSocket client and its filter scope."""

    websocket: WebSocket
    profile_id: str | None = None
    platform: Platform | None = None
    is_public: bool = False
    client_ip: str = ""


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

    @property
    def public_connections_count(self) -> int:
        """Return number of currently registered public WebSocket clients."""
        return sum(1 for sub in self._subscriptions if sub.is_public)

    def get_public_ip_connections_count(self, client_ip: str) -> int:
        """Return number of active public WebSocket connections for a given client IP."""
        return sum(
            1
            for sub in self._subscriptions
            if sub.is_public and sub.client_ip == client_ip
        )

    def can_accept_public(
        self,
        client_ip: str,
        *,
        max_connections: int,
        max_per_ip: int,
    ) -> tuple[bool, str]:
        """Check whether a new public WebSocket connection is within global and per-IP limits."""
        if self.public_connections_count >= max_connections:
            return False, "Policy Violation: Maximum public connections reached"
        if client_ip and self.get_public_ip_connections_count(client_ip) >= max_per_ip:
            return False, "Policy Violation: Maximum connections per IP reached"
        return True, ""

    async def connect(
        self,
        websocket: WebSocket,
        *,
        profile_id: str | None = None,
        platform: Platform | None = None,
        is_public: bool = False,
        client_ip: str = "",
        subprotocol: str | None = None,
        already_accepted: bool = False,
    ) -> WSSubscription:
        """Accept connection, register subscription, and send initial snapshot event."""
        if not already_accepted:
            await websocket.accept(subprotocol=subprotocol)
        sub = WSSubscription(
            websocket=websocket,
            profile_id=profile_id,
            platform=platform,
            is_public=is_public,
            client_ip=client_ip,
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
                public_only=sub.is_public,
                now=ts,
            )
            data: Any = pstats if pstats is not None else {}
        else:
            gstats = self.aggregator.get_global_stats(
                platform_filter=sub.platform,
                public_only=sub.is_public,
                now=ts,
            )
            data = {
                "profiles": {
                    pid: prof.model_dump(mode="json")
                    for pid, prof in gstats.profiles.items()
                }
            }
            if sub.platform is None or sub.platform == Platform.CRYPTO:
                crypto_summary = self.aggregator.get_global_crypto_summary(
                    public_only=sub.is_public
                )
                if crypto_summary.accounts:
                    data["crypto"] = crypto_summary.model_dump(mode="json")

        envelope = WSEventEnvelope(
            event=WSEventType.SNAPSHOT,
            timestamp=ts,
            scope=WSScope(profile_id=sub.profile_id, platform=sub.platform),
            data=data,
        )
        await self._safe_send(sub, envelope.model_dump(mode="json"))

    def _build_public_metric_update(
        self,
        update_data: MetricUpdateData,
    ) -> MetricUpdateData | None:
        """
        Return a sanitized MetricUpdateData for public WebSocket subscribers,
        or None if the account is not public/enabled or if only private fields changed.
        """
        if update_data.account.status == CollectorStatus.DISABLED:
            return None
        if not self.aggregator.is_account_public(
            update_data.profile_id,
            update_data.platform,
            update_data.account.account_key,
        ):
            return None

        if update_data.platform == Platform.KEYCOUNTER:
            public_changes = {
                k: v
                for k, v in update_data.changes.items()
                if k not in KEYCOUNTER_PRIVATE_ONLY_FIELDS
            }
        else:
            public_changes = dict(update_data.changes)

        if not public_changes and not update_data.is_new_latest_post:
            return None

        pconfig = self.aggregator.registry.get_profile(update_data.profile_id)
        if pconfig is not None:
            acc_cfgs = pconfig.accounts.get(str(update_data.platform), [])
            public_summary = self.aggregator.build_platform_summary(
                update_data.platform,
                acc_cfgs,
                public_only=True,
            )
        elif update_data.profile_id == "global" and update_data.platform == Platform.CRYPTO:
            public_summary = self.aggregator.get_global_crypto_summary(public_only=True)
        else:
            public_summary = update_data.platform_summary.model_copy(
                update={
                    "pulsations_today": None,
                    "pulsations_last_1h": None,
                    "clicks_today": None,
                    "clicks_last_1h": None,
                    "accounts": [
                        sanitize_account_state_for_public(a)
                        for a in update_data.platform_summary.accounts
                        if a.status != CollectorStatus.DISABLED
                    ],
                }
            )

        return update_data.model_copy(
            update={
                "account": sanitize_account_state_for_public(update_data.account),
                "platform_summary": public_summary,
                "changes": public_changes,
            }
        )

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
        matching_subs = [
            sub
            for sub in list(self._subscriptions)
            if (sub.profile_id is None or sub.profile_id == update_data.profile_id)
            and (sub.platform is None or sub.platform == update_data.platform)
        ]
        if not matching_subs:
            return

        private_targets = [sub for sub in matching_subs if not sub.is_public]
        public_targets = [sub for sub in matching_subs if sub.is_public]

        coros = []
        if private_targets:
            private_envelope = WSEventEnvelope(
                event=WSEventType.METRIC_UPDATE,
                timestamp=ts,
                scope=WSScope(
                    profile_id=update_data.profile_id,
                    platform=update_data.platform,
                ),
                data=update_data,
            )
            private_payload = private_envelope.model_dump(mode="json")
            for sub in private_targets:
                coros.append(self._safe_send(sub, private_payload))

        if public_targets:
            public_update = self._build_public_metric_update(update_data)
            if public_update is not None:
                public_envelope = WSEventEnvelope(
                    event=WSEventType.METRIC_UPDATE,
                    timestamp=ts,
                    scope=WSScope(
                        profile_id=update_data.profile_id,
                        platform=update_data.platform,
                    ),
                    data=public_update,
                )
                public_payload = public_envelope.model_dump(mode="json")
                for sub in public_targets:
                    coros.append(self._safe_send(sub, public_payload))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def broadcast_collector_status(
        self,
        status_data: CollectorStatusData,
        *,
        now: datetime | None = None,
    ) -> None:
        """Broadcast a collector_status event exclusively to private authenticated subscribers."""
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
            if not sub.is_public
            and (sub.profile_id is None or sub.profile_id == status_data.profile_id)
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
