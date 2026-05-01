"""MQTT listener for edge-published alerts (e.g., autopilot STATUSTEXT)."""
from __future__ import annotations

import logging
from uuid import UUID

from backend.services.alert.service import create_alert
from backend.services.telemetry.service import _get_vehicle_org_id
from backend.services.telemetry.websocket_manager import ws_manager
from backend.shared.database.postgres import get_direct_postgres_session
from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.schemas.alert import AlertCategory, AlertCreate, AlertSeverity

logger = logging.getLogger(__name__)


def _parse_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except Exception:
        return None


def _parse_alert_severity(value: object) -> AlertSeverity:
    try:
        return AlertSeverity(str(value).lower())
    except Exception:
        return AlertSeverity.INFO


def _parse_alert_category(value: object) -> AlertCategory:
    try:
        return AlertCategory(str(value).lower())
    except Exception:
        return AlertCategory.CUSTOM


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

        org_uuid = _parse_uuid(org_id)
        if org_uuid is None:
            logger.warning("Skipping alert persistence for %s: invalid organization id %r", topic, org_id)
            return

        alert_data = AlertCreate(
            vehicle_id=_parse_uuid(payload.get("vehicle_id") or vehicle_id),
            severity=_parse_alert_severity(payload.get("severity")),
            category=_parse_alert_category(payload.get("category") or sub),
            title=str(payload.get("title") or f"{sub.title()} alert"),
            message=str(payload.get("message") or ""),
            metadata={
                "source": "mqtt",
                "topic": topic,
                "subtopic": sub,
                "raw_payload": payload,
                **({"reported_source": payload.get("source")} if payload.get("source") is not None else {}),
            },
        )

        try:
            db = await get_direct_postgres_session()
            async with db:
                persisted = await create_alert(db, org_uuid, alert_data)
                await db.commit()
        except Exception as exc:
            logger.error("Failed persisting alert for %s: %s", topic, exc)
            return

        alert_payload = persisted.model_dump(mode="json")
        alert_payload["metadata"] = alert_data.metadata

        # Broadcast to dashboard clients subscribed to alerts:{org_id}
        try:
            await ws_manager.broadcast_alert(str(org_id), alert_payload)
        except Exception as exc:
            logger.error("WS broadcast_alert failed: %s", exc)

    await mqtt.subscribe("aerocommand/+/alert/+/+", _handle)
