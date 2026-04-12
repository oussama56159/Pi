"""
Command & Control business logic.
Validates commands, publishes to MQTT, tracks acknowledgments.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.database.redis import RedisKeys, get_redis
from backend.shared.mqtt_topics import MQTTTopics
from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.schemas.command import (
    CommandAck,
    CommandRequest,
    CommandResponse,
    CommandStatus,
    CommandType,
    MAVLinkCommand,
)

from .models import CommandRecord

logger = logging.getLogger(__name__)

# Commands that require armed state
REQUIRES_ARMED = {CommandType.TAKEOFF, CommandType.LAND, CommandType.RTL, CommandType.GOTO}

# Commands restricted to specific roles
CRITICAL_COMMANDS = {CommandType.EMERGENCY_STOP, CommandType.REBOOT}


async def dispatch_command(
    db: AsyncSession, org_id: UUID, user_id: UUID, data: CommandRequest,
) -> CommandResponse:
    """
    Validate and dispatch a command to a vehicle.
    1. Validate command preconditions
    2. Record command in PostgreSQL
    3. Cache command status in Redis
    4. Publish to MQTT for edge agent
    5. Return command record
    """
    # Pre-flight validation
    await _validate_command(data)

    # Persist command record
    record = CommandRecord(
        vehicle_id=data.vehicle_id,
        organization_id=org_id,
        command=data.command,
        status=CommandStatus.PENDING,
        params=data.params,
        priority=data.priority,
        timeout_seconds=data.timeout_seconds,
        issued_by=user_id,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    issued_at = record.issued_at or datetime.now(timezone.utc)

    # Build MAVLink command payload
    mavlink_cmd = _build_mavlink_command(data)

    # Publish to MQTT
    mqtt_payload = {
        "command_id": str(record.id),
        "command": data.command.value,
        "mavlink": mavlink_cmd.model_dump() if mavlink_cmd else None,
        "params": data.params,
        "priority": data.priority,
        "timeout": data.timeout_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    topic = MQTTTopics.command_request(str(org_id), str(data.vehicle_id))
    logger.info(f"Publishing command {record.id} to {topic}: {data.command.value}")

    # Publish to MQTT for edge agent
    try:
        mqtt = await get_mqtt()
        await mqtt.publish(topic, mqtt_payload)
    except Exception as exc:
        logger.error("Failed to publish command %s to MQTT: %s", record.id, exc)
        raise HTTPException(status_code=503, detail="Command dispatch unavailable (MQTT offline)")

    # Cache command status in Redis for fast ack matching
    try:
        redis = get_redis()
        await redis.hset(RedisKeys.command(str(record.id)), mapping={
            "status": CommandStatus.SENT.value,
            "vehicle_id": str(data.vehicle_id),
            "command": data.command.value,
            "issued_at": issued_at.isoformat(),
        })
        await redis.expire(RedisKeys.command(str(record.id)), data.timeout_seconds + 60)
    except RuntimeError:
        pass

    # Update status to SENT
    record.status = CommandStatus.SENT
    await db.flush()

    # Start timeout watcher
    asyncio.create_task(_command_timeout_watcher(str(record.id), data.timeout_seconds))

    return CommandResponse.model_validate(record)


async def handle_command_ack(ack: CommandAck) -> None:
    """Process command acknowledgment from edge agent (via MQTT)."""
    try:
        redis = get_redis()
        key = RedisKeys.command(ack.command_id)
        await redis.hset(key, mapping={
            "status": ack.status.value,
            "result_code": str(ack.result_code),
            "message": ack.message or "",
            "ack_at": ack.timestamp.isoformat(),
        })
    except RuntimeError:
        pass

    logger.info(f"Command {ack.command_id} acknowledged: {ack.status.value}")


async def get_command(db: AsyncSession, org_id: UUID, command_id: UUID) -> CommandResponse:
    result = await db.execute(
        select(CommandRecord).where(CommandRecord.id == command_id, CommandRecord.organization_id == org_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Command not found")
    return CommandResponse.model_validate(record)


async def list_commands(
    db: AsyncSession, org_id: UUID, vehicle_id: UUID | None = None, limit: int = 50,
) -> list[CommandResponse]:
    query = select(CommandRecord).where(CommandRecord.organization_id == org_id)
    if vehicle_id:
        query = query.where(CommandRecord.vehicle_id == vehicle_id)
    query = query.order_by(CommandRecord.issued_at.desc()).limit(limit)
    result = await db.execute(query)
    return [CommandResponse.model_validate(r) for r in result.scalars().all()]


# ── Internal helpers ──

async def _validate_command(data: CommandRequest) -> None:
    """Validate command preconditions."""
    # Check vehicle is online
    try:
        redis = get_redis()
        status = await redis.get(RedisKeys.vehicle_status(str(data.vehicle_id)))
        if status != "online":
            raise HTTPException(status_code=409, detail="Vehicle is offline")
    except RuntimeError:
        pass  # Redis down, skip check


def _build_mavlink_command(data: CommandRequest) -> MAVLinkCommand | None:
    """Translate CommandRequest to MAVLink command."""
    cmd_map = MAVLinkCommand.COMMAND_MAP
    cmd_name = data.command.value
    if cmd_name not in cmd_map:
        return None

    cmd = MAVLinkCommand(command_id=cmd_map[cmd_name])

    if data.command == CommandType.ARM:
        cmd.param1 = 1
    elif data.command == CommandType.DISARM:
        cmd.param1 = 0
    elif data.command == CommandType.TAKEOFF:
        # Default to a low, safe hover takeoff height unless overridden.
        # MAV_CMD_NAV_TAKEOFF uses param7 as the target altitude in meters.
        cmd.param7 = float(data.params.get("altitude", 1.0))
    elif data.command == CommandType.GOTO:
        cmd.param5 = data.params.get("lat", 0)
        cmd.param6 = data.params.get("lng", 0)
        cmd.param7 = data.params.get("alt", 0)
    elif data.command == CommandType.EMERGENCY_STOP:
        cmd.param1 = 0  # disarm
        cmd.param2 = 21196  # magic number for force disarm

    return cmd


async def _command_timeout_watcher(command_id: str, timeout: int) -> None:
    """Background task to mark timed-out commands."""
    await asyncio.sleep(timeout)
    try:
        redis = get_redis()
        status = await redis.hget(RedisKeys.command(command_id), "status")
        if status in (CommandStatus.PENDING.value, CommandStatus.SENT.value):
            await redis.hset(RedisKeys.command(command_id), "status", CommandStatus.TIMEOUT.value)
            logger.warning(f"Command {command_id} timed out after {timeout}s")
    except RuntimeError:
        pass

