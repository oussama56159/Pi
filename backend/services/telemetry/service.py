"""
Telemetry processing pipeline.
Receives raw telemetry from MQTT, processes it, and distributes to:
  1. MongoDB – time-series persistence
  2. Redis – latest snapshot cache
  3. WebSocket – real-time dashboard push
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from backend.shared.database.mongo import get_mongo_db
from backend.shared.database.redis import RedisKeys, get_redis
from backend.shared.database.postgres import get_direct_postgres_session, get_postgres_session
from backend.shared.schemas.telemetry import TelemetryFrame, TelemetrySnapshot

from backend.services.fleet.models import Vehicle
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
        _store_in_mongodb(frame),
        _cache_in_redis(frame),
        _broadcast_via_websocket(vehicle_id, frame),
        return_exceptions=True,
    )


async def _store_in_mongodb(frame: TelemetryFrame) -> None:
    """Persist telemetry frame to MongoDB time-series collection."""
    try:
        db = get_mongo_db()
        collection = db["telemetry"]
        doc = frame.model_dump()
        doc["timestamp"] = frame.timestamp
        await collection.insert_one(doc)
    except Exception as e:
        logger.error(f"MongoDB write failed for {frame.vehicle_id}: {e}")


async def _cache_in_redis(frame: TelemetryFrame) -> None:
    """Cache latest telemetry snapshot in Redis for fast lookups."""
    try:
        redis = get_redis()
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
        await redis.hset(
            RedisKeys.telemetry(frame.vehicle_id),
            mapping={k: str(v) for k, v in snapshot.model_dump().items()},
        )
        await redis.expire(RedisKeys.telemetry(frame.vehicle_id), 300)  # 5-min TTL
    except Exception as e:
        logger.error(f"Redis cache failed for {frame.vehicle_id}: {e}")


async def _broadcast_via_websocket(vehicle_id: str, frame: TelemetryFrame) -> None:
    """Push telemetry to connected dashboard WebSocket clients."""
    try:
        data = frame.model_dump(mode="json")
        org_id = await _get_vehicle_org_id(vehicle_id)
        await ws_manager.broadcast_telemetry(vehicle_id, org_id or "default", data)
    except Exception as e:
        logger.error(f"WebSocket broadcast failed for {vehicle_id}: {e}")


async def process_heartbeat(vehicle_id: str, payload: dict) -> None:
    """Process heartbeat message – update vehicle online status."""
    try:
        heartbeat_connected = bool(payload.get("connected", True))
        redis = get_redis()
        await redis.setex(
            RedisKeys.heartbeat(vehicle_id),
            30,  # 30-second TTL – if heartbeat stops, key expires
            datetime.now(timezone.utc).isoformat(),
        )
        await redis.setex(
            RedisKeys.vehicle_status(vehicle_id),
            60,
            "online" if heartbeat_connected else "offline",
        )

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
    """Query telemetry history from MongoDB."""
    try:
        db = get_mongo_db()
        collection = db["telemetry"]
        cursor = collection.find(
            {
                "vehicle_id": vehicle_id,
                "timestamp": {"$gte": start_time, "$lte": end_time},
            },
            {"_id": 0},
        ).sort("timestamp", 1)
        return await cursor.to_list(length=10000)
    except Exception as e:
        logger.error(f"Telemetry history query failed: {e}")
        return []


async def get_latest_snapshot(vehicle_id: str) -> dict | None:
    """Get latest telemetry snapshot from Redis."""
    try:
        redis = get_redis()
        data = await redis.hgetall(RedisKeys.telemetry(vehicle_id))
        return data if data else None
    except Exception:
        return None

