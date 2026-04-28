"""
WebSocket connection manager for real-time telemetry streaming.
Manages per-vehicle and fleet-wide subscriptions from dashboard clients.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TelemetryWebSocketManager:
    """
    Manages WebSocket connections and channel-based subscriptions.

    Channels:
        vehicle:{vehicle_id}  – single vehicle telemetry
        fleet:{fleet_id}      – all vehicles in a fleet
        org:{org_id}          – all vehicles in an organization
        alerts:{org_id}       – alert stream
    """

    def __init__(self):
        # channel_name -> set of WebSocket connections
        self._subscriptions: dict[str, set[WebSocket]] = defaultdict(set)
        # ws -> set of channels
        self._ws_channels: dict[WebSocket, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channels: list[str]) -> None:
        """Accept a WebSocket connection and subscribe to channels."""
        await ws.accept()
        async with self._lock:
            for channel in channels:
                self._subscriptions[channel].add(ws)
                self._ws_channels[ws].add(channel)
        logger.info(f"WS connected: subscribed to {channels}")

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from all subscriptions."""
        async with self._lock:
            channels = self._ws_channels.pop(ws, set())
            for channel in channels:
                self._subscriptions[channel].discard(ws)
                if not self._subscriptions[channel]:
                    del self._subscriptions[channel]
        logger.info(f"WS disconnected: removed from {len(channels)} channels")

    async def subscribe(self, ws: WebSocket, channels: list[str]) -> None:
        """Subscribe an existing connection to additional channels."""
        if not channels:
            return
        async with self._lock:
            for channel in channels:
                self._subscriptions[channel].add(ws)
                self._ws_channels[ws].add(channel)

    async def unsubscribe(self, ws: WebSocket, channels: list[str]) -> None:
        """Unsubscribe an existing connection from channels."""
        if not channels:
            return
        async with self._lock:
            for channel in channels:
                self._subscriptions[channel].discard(ws)
                if ws in self._ws_channels:
                    self._ws_channels[ws].discard(channel)

    async def broadcast_to_channel(self, channel: str, data: dict) -> None:
        """Send data to all WebSocket connections subscribed to a channel."""
        subscribers = self._subscriptions.get(channel, set()).copy()
        if not subscribers:
            return

        message = json.dumps(data)
        dead_connections = []

        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)

        # Clean up dead connections
        for ws in dead_connections:
            await self.disconnect(ws)

    async def broadcast_telemetry(self, vehicle_id: str, org_id: str, data: dict) -> None:
        """Broadcast telemetry to all relevant channels."""
        # Send to vehicle-specific subscribers
        await self.broadcast_to_channel(f"vehicle:{vehicle_id}", {
            "type": "telemetry",
            "vehicle_id": vehicle_id,
            "data": data,
        })

        # Send to org-wide subscribers
        await self.broadcast_to_channel(f"org:{org_id}", {
            "type": "telemetry",
            "vehicle_id": vehicle_id,
            "data": data,
        })

    async def broadcast_alert(self, org_id: str, alert: dict) -> None:
        """Broadcast alert to org subscribers."""
        await self.broadcast_to_channel(f"alerts:{org_id}", {
            "type": "alert",
            "data": alert,
        })

    async def broadcast_mission(self, vehicle_id: str, org_id: str, data: dict) -> None:
        """Broadcast mission assignment/status updates."""
        await self.broadcast_to_channel(f"vehicle:{vehicle_id}", {
            "type": "mission",
            "vehicle_id": vehicle_id,
            "data": data,
        })
        await self.broadcast_to_channel(f"org:{org_id}", {
            "type": "mission",
            "vehicle_id": vehicle_id,
            "data": data,
        })

    @property
    def connection_count(self) -> int:
        return len(self._ws_channels)

    @property
    def channel_count(self) -> int:
        return len(self._subscriptions)


# Singleton instance
ws_manager = TelemetryWebSocketManager()

