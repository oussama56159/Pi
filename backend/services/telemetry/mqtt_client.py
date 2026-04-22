"""
MQTT Client for the Telemetry Service.
Subscribes to telemetry topics from all edge agents,
processes incoming MAVLink-derived data, and fans out to:
    1. PostgreSQL (time-series persistence)
    2. In-memory cache (latest snapshot)
    3. WebSocket manager (real-time dashboard push)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

import aiomqtt

from backend.shared.config import get_base_settings
from backend.shared.mqtt_topics import MQTTTopics

logger = logging.getLogger(__name__)


class TelemetryMQTTClient:
    """Async MQTT client for telemetry ingestion."""

    def __init__(self, org_id: str, on_telemetry: Callable, on_heartbeat: Callable):
        self.org_id = org_id
        self.on_telemetry = on_telemetry
        self.on_heartbeat = on_heartbeat
        self._running = False
        self._client: aiomqtt.Client | None = None

    async def start(self) -> None:
        """Connect to MQTT broker and begin listening."""
        settings = get_base_settings()
        self._running = True

        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=settings.MQTT_BROKER_HOST,
                    port=settings.MQTT_BROKER_PORT,
                    username=settings.MQTT_USERNAME,
                    password=settings.MQTT_PASSWORD,
                    identifier=f"{settings.MQTT_CLIENT_ID_PREFIX}-telemetry-{self.org_id}",
                    clean_session=True,
                ) as client:
                    self._client = client
                    logger.info(f"Connected to MQTT broker at {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")

                    # Subscribe to all raw telemetry for this org
                    await client.subscribe(MQTTTopics.all_telemetry(self.org_id), qos=settings.MQTT_QOS)
                    await client.subscribe(MQTTTopics.all_heartbeats(self.org_id), qos=0)

                    logger.info(f"Subscribed to telemetry topics for org {self.org_id}")

                    async for message in client.messages:
                        await self._handle_message(message)

            except aiomqtt.MqttError as e:
                logger.error(f"MQTT connection lost: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.exception(f"Unexpected MQTT error: {e}")
                await asyncio.sleep(5)

    async def _handle_message(self, message: aiomqtt.Message) -> None:
        """Route incoming MQTT messages to the appropriate handler."""
        topic = str(message.topic)
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid payload on {topic}: {e}")
            return

        # Parse topic: aerocommand/{org_id}/telemetry/{vehicle_id}/{sub}
        parts = topic.split("/")
        if len(parts) < 5:
            return

        vehicle_id = parts[3]
        sub_topic = parts[4]

        if sub_topic == "raw":
            await self.on_telemetry(vehicle_id, payload)
        elif sub_topic == "heartbeat":
            await self.on_heartbeat(vehicle_id, payload)

    async def stop(self) -> None:
        self._running = False
        if self._client:
            # aiomqtt handles disconnect on context exit
            self._client = None

