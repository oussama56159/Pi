"""
Shared async MQTT client wrapper for microservices.
Provides publish/subscribe with automatic reconnection.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import aiomqtt

from backend.shared.config import get_base_settings
from backend.shared.retry import retry_async

logger = logging.getLogger(__name__)


class MQTTService:
    """
    Reusable async MQTT client for any microservice.

    Usage:
        mqtt = MQTTService(client_id="telemetry-svc")
        await mqtt.start()
        await mqtt.subscribe("aerocommand/+/telemetry/#", handler)
        await mqtt.publish("aerocommand/org/command/v1/request", payload)
    """

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._client: aiomqtt.Client | None = None
        self._publish_queue: asyncio.Queue = asyncio.Queue()
        self._connection_task: asyncio.Task | None = None
        self._publish_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to MQTT broker and start listener + publisher tasks."""
        self._running = True
        if self._connection_task is None or self._connection_task.done():
            self._connection_task = asyncio.create_task(self._connection_loop())
        if self._publish_task is None or self._publish_task.done():
            self._publish_task = asyncio.create_task(self._publish_loop())

    async def stop(self) -> None:
        self._running = False

        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass

        for task in (self._publish_task, self._connection_task):
            if task is not None and not task.done():
                task.cancel()

        for task in (self._publish_task, self._connection_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

        self._client = None
        self._publish_task = None
        self._connection_task = None

    async def subscribe(self, topic: str, handler: Callable) -> None:
        """Register a handler for a topic pattern."""
        self._handlers[topic] = handler
        if self._client:
            settings = get_base_settings()
            await retry_async(
                lambda: self._client.subscribe(topic, qos=settings.MQTT_QOS),
                retries=3,
                base_delay_s=0.2,
                retry_on=(aiomqtt.MqttError,),
            )
            logger.info(f"Subscribed to {topic}")

    async def publish(self, topic: str, payload: dict | str, qos: int | None = None, retain: bool = False) -> None:
        """Queue a message for publishing."""
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        await self._publish_queue.put((topic, payload, qos, retain))

    async def _connection_loop(self) -> None:
        """Maintain persistent MQTT connection with auto-reconnect."""
        settings = get_base_settings()

        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=settings.MQTT_BROKER_HOST,
                    port=settings.MQTT_BROKER_PORT,
                    username=settings.MQTT_USERNAME,
                    password=settings.MQTT_PASSWORD,
                    identifier=f"{settings.MQTT_CLIENT_ID_PREFIX}-{self.client_id}",
                    keepalive=settings.MQTT_KEEPALIVE,
                    clean_session=True,
                ) as client:
                    self._client = client
                    logger.info(f"MQTT connected: {self.client_id}")

                    # Re-subscribe to all registered topics
                    for topic in self._handlers:
                        await retry_async(
                            lambda topic=topic: client.subscribe(topic, qos=settings.MQTT_QOS),
                            retries=3,
                            base_delay_s=0.2,
                            retry_on=(aiomqtt.MqttError,),
                        )

                    # Listen for messages
                    async for message in client.messages:
                        await self._dispatch(message)

            except aiomqtt.MqttError as e:
                logger.error(f"MQTT connection error: {e}. Reconnecting with backoff...")
                self._client = None
                await asyncio.sleep(1.5)
            except Exception as e:
                logger.exception(f"MQTT unexpected error: {e}")
                self._client = None
                await asyncio.sleep(5)

    async def _publish_loop(self) -> None:
        """Drain publish queue and send messages."""
        settings = get_base_settings()

        while self._running:
            try:
                topic, payload, qos, retain = await asyncio.wait_for(
                    self._publish_queue.get(), timeout=1.0
                )
                if self._client:
                    await retry_async(
                        lambda: self._client.publish(
                            topic,
                            payload.encode("utf-8") if isinstance(payload, str) else payload,
                            qos=qos if qos is not None else settings.MQTT_QOS,
                            retain=retain,
                        ),
                        retries=3,
                        base_delay_s=0.2,
                        retry_on=(aiomqtt.MqttError,),
                    )
                else:
                    # Re-queue if not connected
                    await self._publish_queue.put((topic, payload, qos, retain))
                    await asyncio.sleep(1)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Publish error: {e}")

    async def _dispatch(self, message: aiomqtt.Message) -> None:
        """Route incoming message to matching handler."""
        topic_str = str(message.topic)
        for pattern, handler in self._handlers.items():
            if self._topic_matches(topic_str, pattern):
                try:
                    payload = json.loads(message.payload.decode("utf-8"))
                    await handler(topic_str, payload)
                except Exception as e:
                    logger.error(f"Handler error for {topic_str}: {e}")
                break

    @staticmethod
    def _topic_matches(topic: str, pattern: str) -> bool:
        """Simple MQTT topic matching with + and # wildcards."""
        topic_parts = topic.split("/")
        pattern_parts = pattern.split("/")

        for i, pp in enumerate(pattern_parts):
            if pp == "#":
                return True
            if i >= len(topic_parts):
                return False
            if pp != "+" and pp != topic_parts[i]:
                return False

        return len(topic_parts) == len(pattern_parts)

