"""
Telemetry processing pipeline.
Receives raw telemetry from MQTT, processes it, and distributes to:
    1. PostgreSQL – time-series persistence
    2. In-memory cache – latest snapshot and heartbeat state
    3. WebSocket – real-time dashboard push
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from backend.shared.database.postgres import get_direct_postgres_session, get_postgres_session
from backend.shared.runtime_cache import get_runtime_cache
from backend.shared.schemas.telemetry import TelemetryFrame, TelemetrySnapshot

from backend.services.alert.service import create_alert, evaluate_telemetry_against_rules
from backend.services.fleet.models import Vehicle
from backend.services.telemetry.models import TelemetryHistoryRecord
from backend.shared.schemas.vehicle import VehicleStatus
from sqlalchemy import select

from .websocket_manager import ws_manager

logger = logging.getLogger(__name__)

_vehicle_org_cache: dict[str, str] = {}


async def _get_vehicle_org_id(vehicle_id: str) -> str | None:
    """Resolve a vehicle's org_id for org-scoped WebSocket broadcasts."""
    cached = _vehicle_org_cache.get(vehicle_id)
    if cached:
        return cached

    try:
        vehicle_uuid = UUID(vehicle_id)
    except Exception:
        return None

    try:
        async for db in get_postgres_session():
            result = await db.execute(select(Vehicle.organization_id).where(Vehicle.id == vehicle_uuid))
            org_id = result.scalar_one_or_none()
            if org_id:
                _vehicle_org_cache[vehicle_id] = str(org_id)
                return _vehicle_org_cache[vehicle_id]
            break
    except Exception:
        return None
    return None


async def process_telemetry(vehicle_id: str, payload: dict) -> None:
    """
    Main telemetry processing pipeline.
    Called by MQTT client when raw telemetry arrives.
    """
    try:
        frame = TelemetryFrame.model_validate(payload)
    except Exception as e:
        logger.warning(f"Invalid telemetry frame from {vehicle_id}: {e}")
        return

    # Pipeline stages run concurrently
    import asyncio
    await asyncio.gather(
        _sync_vehicle_state_from_frame(vehicle_id, frame),
        _store_in_postgres(frame),
        _cache_in_memory(frame),
        _broadcast_via_websocket(vehicle_id, frame),
        _evaluate_and_persist_alerts(frame),
        return_exceptions=True,
    )


async def _store_in_postgres(frame: TelemetryFrame) -> None:
    """Persist telemetry frame to PostgreSQL time-series table."""
    try:
        org_id = await _get_vehicle_org_id(frame.vehicle_id)
        record = TelemetryHistoryRecord(
            vehicle_id=UUID(frame.vehicle_id),
            organization_id=UUID(org_id) if org_id else None,
            timestamp=frame.timestamp,
            payload=frame.model_dump(mode="json"),
        )
        db = await get_direct_postgres_session()
        async with db:
            db.add(record)
            await db.commit()
    except Exception as e:
        logger.error(f"PostgreSQL write failed for {frame.vehicle_id}: {e}")


async def _cache_in_memory(frame: TelemetryFrame) -> None:
    """Cache latest telemetry snapshot in memory for fast lookups."""
    try:
        alt = frame.altitude if frame.altitude is not None else frame.gps.alt
        snapshot = TelemetrySnapshot(
            vehicle_id=frame.vehicle_id,
            timestamp=frame.timestamp,
            lat=frame.gps.lat,
            lng=frame.gps.lng,
            alt=alt,
            heading=frame.heading,
            groundspeed=frame.groundspeed,
            battery=frame.battery.remaining,
            temperature=frame.battery.temperature,
            mode=frame.system.mode,
            armed=frame.system.armed,
            satellites=frame.gps.satellites_visible,
            gps_fix=frame.gps.fix_type,
        )
        await get_runtime_cache().store_telemetry_snapshot(
            frame.vehicle_id,
            snapshot.model_dump(),
            ttl_seconds=300,
        )
    except Exception as e:
        logger.error(f"In-memory cache failed for {frame.vehicle_id}: {e}")


async def _broadcast_via_websocket(vehicle_id: str, frame: TelemetryFrame) -> None:
    """Push telemetry to connected dashboard WebSocket clients."""
    try:
        data = frame.model_dump(mode="json")
        org_id = await _get_vehicle_org_id(vehicle_id)
        await ws_manager.broadcast_telemetry(vehicle_id, org_id or "default", data)
    except Exception as e:
        logger.error(f"WebSocket broadcast failed for {vehicle_id}: {e}")


async def _evaluate_and_persist_alerts(frame: TelemetryFrame) -> None:
    """Evaluate telemetry rules and persist any generated alerts."""
    try:
        org_id = await _get_vehicle_org_id(frame.vehicle_id)
        if not org_id:
            return

        org_uuid = UUID(org_id)
        db = await get_direct_postgres_session()
        persisted_alerts: list[dict] = []

        async with db:
            triggered_alerts = await evaluate_telemetry_against_rules(db, org_uuid, frame)
            if not triggered_alerts:
                return

            for alert_data in triggered_alerts:
                metadata = dict(alert_data.metadata or {})
                metadata.setdefault("source", "telemetry")
                metadata.setdefault("vehicle_id", frame.vehicle_id)
                if metadata.get("rule_id") is not None:
                    metadata["rule_id"] = str(metadata["rule_id"])
                if metadata.get("zone_id") is not None:
                    metadata["zone_id"] = str(metadata["zone_id"])

                persisted = await create_alert(
                    db,
                    org_uuid,
                    alert_data.model_copy(update={"metadata": metadata}),
                )
                payload = persisted.model_dump(mode="json")
                payload["metadata"] = metadata
                persisted_alerts.append(payload)

            await db.commit()

        for alert_payload in persisted_alerts:
            await ws_manager.broadcast_alert(org_id, alert_payload)
    except Exception as e:
        logger.error(f"Telemetry alert evaluation failed for {frame.vehicle_id}: {e}")


async def process_heartbeat(vehicle_id: str, payload: dict) -> None:
    """Process heartbeat message – update vehicle online status."""
    try:
        heartbeat_connected = bool(payload.get("connected", True))
        cache = get_runtime_cache()
        await cache.set_heartbeat(vehicle_id, datetime.now(timezone.utc).isoformat(), ttl_seconds=30)
        await cache.set_vehicle_status(vehicle_id, "online" if heartbeat_connected else "offline", ttl_seconds=60)

        if heartbeat_connected:
            await _sync_vehicle_online_state(vehicle_id)
    except Exception as e:
        logger.error(f"Heartbeat processing failed for {vehicle_id}: {e}")


async def _sync_vehicle_state_from_frame(vehicle_id: str, frame: TelemetryFrame) -> None:
    """Persist live telemetry into the vehicle registry so fleet views stay current."""
    try:
        mode = frame.system.mode.upper()
        armed = bool(frame.system.armed)
        alt = frame.altitude if frame.altitude is not None else frame.gps.alt
        moving = frame.groundspeed > 0.5 or abs(frame.climb_rate) > 0.1 or alt > 0.5

        if armed:
            if mode == "LAND":
                status = VehicleStatus.LANDING
            elif mode == "RTL":
                status = VehicleStatus.RETURNING
            elif moving or mode in {"AUTO", "GUIDED", "MISSION", "OFFBOARD"}:
                status = VehicleStatus.IN_FLIGHT
            else:
                status = VehicleStatus.ARMED
        elif mode == "LAND":
            status = VehicleStatus.LANDING
        elif mode == "RTL":
            status = VehicleStatus.RETURNING
        else:
            status = VehicleStatus.IDLE

        db = await get_direct_postgres_session()
        async with db:
            result = await db.execute(select(Vehicle).where(Vehicle.id == UUID(vehicle_id)))
            vehicle = result.scalar_one_or_none()
            if not vehicle:
                return

            vehicle.current_lat = frame.gps.lat
            vehicle.current_lng = frame.gps.lng
            vehicle.current_alt = alt
            vehicle.battery = frame.battery.remaining
            vehicle.gps_fix = frame.gps.fix_type
            vehicle.satellites = frame.gps.satellites_visible
            vehicle.mode = frame.system.mode
            vehicle.armed = frame.system.armed
            vehicle.status = status
            vehicle.last_seen = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.debug(f"Vehicle registry sync skipped for {vehicle_id}: {e}")


async def _sync_vehicle_online_state(vehicle_id: str) -> None:
    """Mark a vehicle online in Postgres when heartbeat confirms connectivity."""
    try:
        db = await get_direct_postgres_session()
        async with db:
            result = await db.execute(select(Vehicle).where(Vehicle.id == UUID(vehicle_id)))
            vehicle = result.scalar_one_or_none()
            if not vehicle:
                return

            if vehicle.status == VehicleStatus.OFFLINE:
                vehicle.status = VehicleStatus.IDLE
            vehicle.last_seen = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.debug(f"Vehicle online-state sync skipped for {vehicle_id}: {e}")


async def get_telemetry_history(
    vehicle_id: str, start_time: datetime, end_time: datetime, resolution: str = "1s",
) -> list[dict]:
    """Query telemetry history from PostgreSQL."""
    try:
        db = await get_direct_postgres_session()
        async with db:
            result = await db.execute(
                select(TelemetryHistoryRecord.payload)
                .where(
                    TelemetryHistoryRecord.vehicle_id == UUID(vehicle_id),
                    TelemetryHistoryRecord.timestamp >= start_time,
                    TelemetryHistoryRecord.timestamp <= end_time,
                )
                .order_by(TelemetryHistoryRecord.timestamp.asc())
                .limit(10000)
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(f"Telemetry history query failed: {e}")
        return []


async def get_latest_snapshot(vehicle_id: str) -> dict | None:
    """Get latest telemetry snapshot from in-memory cache."""
    try:
        return await get_runtime_cache().get_telemetry_snapshot(vehicle_id)
    except Exception:
        return None

