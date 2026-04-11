"""MQTT listener for command acknowledgments from edge agents."""
from __future__ import annotations

import logging

from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.schemas.command import CommandAck

from .service import handle_command_ack

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
