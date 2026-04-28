"""MQTT listener for telemetry + heartbeat messages."""
from __future__ import annotations

import logging

from backend.shared.mqtt_runtime import get_mqtt

from .service import process_telemetry, process_heartbeat

logger = logging.getLogger(__name__)


async def start_telemetry_listener() -> None:
    """Subscribe to telemetry topics and route messages into the telemetry pipeline.

    Expected topics:
      - aerocommand/{org_id}/telemetry/{vehicle_id}/raw
      - aerocommand/{org_id}/telemetry/{vehicle_id}/heartbeat
      - aerocommand/{org_id}/status/{vehicle_id}/online

    Note: This function registers handlers and returns; the shared MQTT runtime
    keeps the connection alive in the background.
    """

    mqtt = await get_mqtt()

    async def _handle(topic: str, payload: dict) -> None:
        parts = topic.split("/")
        if len(parts) < 5:
            return

        domain = parts[2]
        vehicle_id = parts[3]
        sub = parts[4]

        try:
            if domain == "telemetry" and sub == "raw":
                await process_telemetry(vehicle_id, payload)
            elif domain == "telemetry" and sub == "heartbeat":
                await process_heartbeat(vehicle_id, payload)
            elif domain == "status" and sub == "online":
                await process_heartbeat(vehicle_id, {"connected": bool(payload.get("online", True))})
        except Exception as exc:
            logger.error("Telemetry MQTT handler failed for %s: %s", topic, exc)

    await mqtt.subscribe("aerocommand/+/telemetry/+/raw", _handle)
    await mqtt.subscribe("aerocommand/+/telemetry/+/heartbeat", _handle)
    await mqtt.subscribe("aerocommand/+/status/+/online", _handle)
