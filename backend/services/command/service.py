"""
Command & Control business logic.
Validates commands, publishes to MQTT, tracks acknowledgments.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import orjson
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.shared.mqtt_topics import MQTTTopics
from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.runtime_cache import get_runtime_cache
from backend.shared.database.postgres import get_direct_postgres_session
from backend.shared.schemas.command import (
    CommandAck,
    CommandRequest,
    CommandResponse,
    CommandStatus,
    CommandType,
    MAVLinkCommand,
)
from backend.shared.schemas.auth import Role
from backend.shared.schemas.telemetry import TelemetrySnapshot
from backend.services.alert.models import GeofenceZoneRecord
from backend.shared.metrics import COMMAND_DISPATCH_TOTAL, MQTT_PUBLISH_LATENCY_SECONDS

from .models import CommandRecord

logger = logging.getLogger(__name__)

# Commands that require armed state
REQUIRES_ARMED = {CommandType.TAKEOFF, CommandType.LAND, CommandType.RTL, CommandType.GOTO}

# Commands restricted to specific roles
CRITICAL_COMMANDS = {CommandType.EMERGENCY_STOP, CommandType.REBOOT}


async def dispatch_command(
    db: AsyncSession, org_id: UUID, user_id: UUID, data: CommandRequest, *, user: dict | None = None
) -> CommandResponse:
    """
    Validate and dispatch a command to a vehicle.
    1. Validate command preconditions
    2. Record command in PostgreSQL
    3. Cache command status in memory
    4. Publish to MQTT for edge agent
    5. Return command record
    """
    # Pre-flight validation
    if not data.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency_key is required")
    await _validate_command(db, org_id, data, user=user)

    fingerprint = _command_fingerprint(data)
    existing = (
        await db.execute(
            select(CommandRecord).where(
                CommandRecord.organization_id == org_id,
                CommandRecord.idempotency_key == data.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used with different command payload")
        return CommandResponse.model_validate(existing)

    request_id = user.get("request_id") if user else None
    # Persist command record
    record = CommandRecord(
        vehicle_id=data.vehicle_id,
        organization_id=org_id,
        command=data.command,
        idempotency_key=data.idempotency_key,
        request_fingerprint=fingerprint,
        status=CommandStatus.PENDING,
        params=data.params,
        priority=data.priority,
        timeout_seconds=data.timeout_seconds,
        issued_by=user_id,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(CommandRecord).where(
                    CommandRecord.organization_id == org_id,
                    CommandRecord.idempotency_key == data.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used with different command payload")
        return CommandResponse.model_validate(existing)
    await db.refresh(record)
    issued_at = record.issued_at or datetime.now(timezone.utc)
    # Make the command row durable before any side effect is emitted.
    await db.commit()

    # Build MAVLink command payload
    mavlink_cmd = _build_mavlink_command(data)

    # Publish to MQTT
    mqtt_payload = {
        "command_id": str(record.id),
        "correlation_id": request_id or str(record.id),
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
        start = time.perf_counter()
        await mqtt.publish(topic, mqtt_payload)
        MQTT_PUBLISH_LATENCY_SECONDS.labels("command").observe(time.perf_counter() - start)
    except Exception as exc:
        COMMAND_DISPATCH_TOTAL.labels(data.command.value, "publish_error").inc()
        logger.error("Failed to publish command %s to MQTT: %s", record.id, exc)
        # Persist failure so operators see real command outcome.
        record.status = CommandStatus.FAILED
        record.error_message = "MQTT publish failed"
        record.completed_at = datetime.now(timezone.utc)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
        raise HTTPException(status_code=503, detail="Command dispatch unavailable (MQTT offline)")

    await get_runtime_cache().set_command_state(
        str(record.id),
        {
            "status": CommandStatus.SENT.value,
            "vehicle_id": str(data.vehicle_id),
            "command": data.command.value,
            "issued_at": issued_at.isoformat(),
        },
        ttl_seconds=data.timeout_seconds + 60,
    )

    # Update status to SENT
    record.status = CommandStatus.SENT
    await db.commit()

    # Start timeout watcher
    asyncio.create_task(_command_timeout_watcher(str(record.id), data.timeout_seconds))
    COMMAND_DISPATCH_TOTAL.labels(data.command.value, "sent").inc()

    return CommandResponse.model_validate(record)


async def handle_command_ack(ack: CommandAck) -> None:
    """Process command acknowledgment from edge agent (via MQTT)."""
    status = ack.status
    now = ack.timestamp
    result_payload = {"result_code": ack.result_code, "message": ack.message or ""}
    terminal_statuses = {
        CommandStatus.REJECTED,
        CommandStatus.FAILED,
        CommandStatus.COMPLETED,
        CommandStatus.TIMEOUT,
    }
    acked_statuses = terminal_statuses | {
        CommandStatus.ACCEPTED,
        CommandStatus.ACKNOWLEDGED,
        CommandStatus.IN_PROGRESS,
    }

    try:
        command_id = UUID(ack.command_id)
    except ValueError:
        logger.error("Invalid command_id in ACK payload: %s", ack.command_id)
        return

    try:
        session = await get_direct_postgres_session()
        async with session:
            row = (
                await session.execute(select(CommandRecord).where(CommandRecord.id == command_id))
            ).scalar_one_or_none()
            if row is not None:
                if row.status in terminal_statuses:
                    return
                row.status = status
                row.result = result_payload
                if status in acked_statuses and row.acknowledged_at is None:
                    row.acknowledged_at = now
                if status in terminal_statuses:
                    row.completed_at = now
                    if status in {CommandStatus.REJECTED, CommandStatus.FAILED, CommandStatus.TIMEOUT}:
                        row.error_message = ack.message or f"Command {status.value}"
                    else:
                        row.error_message = None
                await session.commit()
    except Exception as exc:
        logger.error("Failed persisting command ACK %s: %s", ack.command_id, exc)

    await get_runtime_cache().update_command_state(
        ack.command_id,
        {
            "status": status.value,
            "result_code": str(ack.result_code),
            "message": ack.message or "",
            "ack_at": now.isoformat(),
        },
    )

    logger.info(f"Command {ack.command_id} acknowledged: {status.value}")


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

async def _validate_command(db: AsyncSession, org_id: UUID, data: CommandRequest, *, user: dict | None = None) -> None:
    """Validate command preconditions."""
    # Check vehicle is online
    status = await get_runtime_cache().get_vehicle_status(str(data.vehicle_id))
    if status is not None and status != "online":
        raise HTTPException(status_code=409, detail="Vehicle is offline")

    if data.command in CRITICAL_COMMANDS and user and user.get("role") not in {Role.ADMIN.value, Role.SUPER_ADMIN.value}:
        raise HTTPException(status_code=403, detail="Critical command requires admin role")

    telemetry_raw = await get_runtime_cache().get_telemetry_snapshot(str(data.vehicle_id))
    telemetry = _parse_telemetry_snapshot(telemetry_raw)
    if telemetry is not None and data.command in {CommandType.TAKEOFF, CommandType.MISSION_START, CommandType.GOTO}:
        if telemetry.battery is not None and float(telemetry.battery) < 20.0:
            raise HTTPException(status_code=409, detail="Preflight failed: battery below 20%")
        if telemetry.gps_fix is not None and int(telemetry.gps_fix) < 3:
            raise HTTPException(status_code=409, detail="Preflight failed: GPS fix is insufficient")

    if data.command == CommandType.GOTO:
        lat = float(data.params.get("lat", 0))
        lng = float(data.params.get("lng", 0))
        alt = float(data.params.get("alt", 0))
        await _enforce_geofence(db, org_id, lat=lat, lng=lng, alt=alt)


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
    elif data.command == CommandType.MISSION_START:
        # MAV_CMD_MISSION_START supports optional first/last item as param1/param2.
        cmd.param1 = float(data.params.get("first_item", 0))
        cmd.param2 = float(data.params.get("last_item", 0))
    elif data.command == CommandType.MISSION_PAUSE:
        # MAV_CMD_DO_PAUSE_CONTINUE: 0 pause, 1 continue.
        cmd.param1 = 0
    elif data.command == CommandType.MISSION_RESUME:
        cmd.param1 = 1

    return cmd


async def _command_timeout_watcher(command_id: str, timeout: int) -> None:
    """Background task to mark timed-out commands."""
    await asyncio.sleep(timeout)
    cache = get_runtime_cache()
    state = await cache.get_command_state(command_id)
    if state and state.get("status") in (CommandStatus.PENDING.value, CommandStatus.SENT.value):
        timeout_at = datetime.now(timezone.utc)
        timeout_message = f"Command timed out after {timeout}s"
        try:
            session = await get_direct_postgres_session()
            async with session:
                row = (
                    await session.execute(select(CommandRecord).where(CommandRecord.id == UUID(command_id)))
                ).scalar_one_or_none()
                if row is None:
                    logger.warning("Command %s timed out but no database row was found", command_id)
                elif row.status in {CommandStatus.REJECTED, CommandStatus.FAILED, CommandStatus.COMPLETED, CommandStatus.TIMEOUT}:
                    return
                else:
                    row.status = CommandStatus.TIMEOUT
                    row.completed_at = timeout_at
                    row.error_message = timeout_message
                    await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist timeout for command %s: %s", command_id, exc)

        await cache.update_command_state(
            command_id,
            {
                "status": CommandStatus.TIMEOUT.value,
                "completed_at": timeout_at.isoformat(),
                "error_message": timeout_message,
            },
        )
        logger.warning(f"Command {command_id} timed out after {timeout}s")


def _command_fingerprint(data: CommandRequest) -> str:
    payload = {
        "vehicle_id": str(data.vehicle_id),
        "command": data.command.value,
        "params": data.params,
        "priority": data.priority,
        "timeout_seconds": data.timeout_seconds,
    }
    raw = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(raw).hexdigest()


def _parse_telemetry_snapshot(raw: dict | None) -> TelemetrySnapshot | None:
    if raw is None:
        return None
    try:
        return TelemetrySnapshot.model_validate(raw)
    except Exception:
        return None


def _point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        intersects = ((xi > lng) != (xj > lng)) and (
            lat < (yj - yi) * (lng - xi) / ((xj - xi) or 1e-9) + yi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


async def _enforce_geofence(db: AsyncSession, org_id: UUID, *, lat: float, lng: float, alt: float) -> None:
    zones = (
        await db.execute(
            select(GeofenceZoneRecord).where(
                GeofenceZoneRecord.organization_id == org_id,
                GeofenceZoneRecord.enabled.is_(True),
            )
        )
    ).scalars().all()
    blocking = [z for z in zones if str(z.action).lower() in {"block", "block_start"}]
    if not blocking:
        return
    for zone in blocking:
        coords = zone.coordinates or []
        if zone.type == "polygon" and isinstance(coords, list) and len(coords) >= 3:
            if not _point_in_polygon(lat, lng, coords):
                continue
            if zone.min_altitude is not None and alt < zone.min_altitude:
                raise HTTPException(status_code=409, detail=f"Geofence violation: altitude below {zone.min_altitude}")
            if zone.max_altitude is not None and alt > zone.max_altitude:
                raise HTTPException(status_code=409, detail=f"Geofence violation: altitude above {zone.max_altitude}")
            return
    raise HTTPException(status_code=409, detail="Geofence violation: target point outside allowed zones")

