"""MQTT listener for edge-published alerts (e.g., autopilot STATUSTEXT)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from backend.shared.mqtt_runtime import get_mqtt
from backend.services.telemetry.websocket_manager import ws_manager
from backend.services.telemetry.service import _get_vehicle_org_id

logger = logging.getLogger(__name__)


async def start_alert_listener() -> None:
    """Subscribe to alert topics and forward to the dashboard WebSocket alert stream."""

    mqtt = await get_mqtt()

    async def _handle(topic: str, payload: dict) -> None:
        parts = topic.split("/")
        # aerocommand/{org_id}/alert/{vehicle_id}/{sub}
        if len(parts) < 5:
            return
        if parts[0] != "aerocommand" or parts[2] != "alert":
            return

        org_from_topic = parts[1]
        vehicle_id = parts[3]
        sub = parts[4]
        if sub not in ("system", "battery", "geofence"):
            return

        try:
            org_id = await _get_vehicle_org_id(vehicle_id) or org_from_topic
        except Exception:
            org_id = org_from_topic

        if not isinstance(payload, dict):
            return

        alert = {
            "id": str(payload.get("id") or uuid4()),
            "vehicle_id": str(payload.get("vehicle_id") or vehicle_id),
            "severity": str(payload.get("severity") or "info"),
            "message": str(payload.get("message") or ""),
            "timestamp": str(payload.get("timestamp") or datetime.now(tz=timezone.utc).isoformat()),
            "category": str(payload.get("category") or sub),
            **({"source": payload.get("source")} if payload.get("source") else {}),
        }

        # Broadcast to dashboard clients subscribed to alerts:{org_id}
        try:
            await ws_manager.broadcast_alert(org_id, alert)
        except Exception as exc:
            logger.error("WS broadcast_alert failed: %s", exc)

    await mqtt.subscribe("aerocommand/+/alert/+/+", _handle)
