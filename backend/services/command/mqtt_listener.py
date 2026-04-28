"""MQTT listener for command acknowledgments from edge agents."""
from __future__ import annotations

import logging
from uuid import UUID

from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.mqtt_topics import MQTTTopics
from backend.shared.schemas.command import CommandAck
from backend.shared.schemas.command import CommandStatus
from backend.shared.database.postgres import get_direct_postgres_session
from sqlalchemy import select

from .service import handle_command_ack
from .models import CommandRecord

logger = logging.getLogger(__name__)


async def start_command_ack_listener() -> None:
    """Subscribe to command ack topics and update command status cache."""

    mqtt = await get_mqtt()

    async def _handle(topic: str, payload: dict) -> None:
        parts = topic.split("/")
        if len(parts) < 5:
            return

        # aerocommand/{org_id}/command/{vehicle_id}/ack
        if parts[2] != "command" or parts[4] != "ack":
            return

        try:
            ack = CommandAck.model_validate(payload)
            await handle_command_ack(ack)
        except Exception as exc:
            logger.error("Command ACK MQTT handler failed for %s: %s", topic, exc)

    await mqtt.subscribe("aerocommand/+/command/+/ack", _handle)

    async def _handle_reconcile(topic: str, payload: dict) -> None:
        parts = topic.split("/")
        if len(parts) < 6:
            return
        # aerocommand/{org}/system/{vehicle}/reconcile/request
        if parts[2] != "system" or parts[4] != "reconcile" or parts[5] != "request":
            return
        org_id = parts[1]
        vehicle_id = parts[3]
        try:
            db = await get_direct_postgres_session()
            async with db:
                rows = (
                    await db.execute(
                        select(CommandRecord).where(
                            CommandRecord.organization_id == UUID(org_id),
                            CommandRecord.vehicle_id == UUID(vehicle_id),
                            CommandRecord.status.in_(
                                [CommandStatus.PENDING, CommandStatus.SENT, CommandStatus.ACKNOWLEDGED, CommandStatus.IN_PROGRESS]
                            ),
                        )
                    )
                ).scalars().all()
            replay = [
                {
                    "command_id": str(r.id),
                    "command": r.command.value if hasattr(r.command, "value") else str(r.command),
                    "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                    "issued_at": r.issued_at.isoformat(),
                }
                for r in rows
            ]
            await mqtt.publish(
                MQTTTopics.system_reconcile_response(org_id, vehicle_id),
                {"vehicle_id": vehicle_id, "pending_commands": replay, "ts": payload.get("ts")},
            )
        except Exception as exc:
            logger.error("Reconcile handler failed for %s: %s", topic, exc)

    await mqtt.subscribe("aerocommand/+/system/+/reconcile/request", _handle_reconcile)
