"""Redis-backed runtime cache for distributed safety-critical state."""
from __future__ import annotations

import uuid
from typing import Any

import orjson

from backend.shared.database.redis import get_redis


def _orjson_loads_redis_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return orjson.loads(value)
    if isinstance(value, str):
        return orjson.loads(value.encode("utf-8"))
    return orjson.loads(str(value).encode("utf-8"))

class RedisRuntimeCache:
    def __init__(self) -> None:
        self._redis = get_redis()

    @staticmethod
    def _key_session(user_id: str) -> str:
        return f"aero:session:{user_id}"

    @staticmethod
    def _key_blacklist(jti: str) -> str:
        return f"aero:token:blacklist:{jti}"

    @staticmethod
    def _key_telemetry(vehicle_id: str) -> str:
        return f"aero:telemetry:latest:{vehicle_id}"

    @staticmethod
    def _key_vehicle_status(vehicle_id: str) -> str:
        return f"aero:vehicle:status:{vehicle_id}"

    @staticmethod
    def _key_heartbeat(vehicle_id: str) -> str:
        return f"aero:vehicle:heartbeat:{vehicle_id}"

    @staticmethod
    def _key_rate_limit(client_id: str) -> str:
        return f"aero:rate_limit:{client_id}"

    @staticmethod
    def _key_command_state(command_id: str) -> str:
        return f"aero:command:state:{command_id}"

    async def set_session(self, user_id: str, mapping: dict[str, Any], ttl_seconds: int | float | None = None) -> None:
        key = self._key_session(user_id)
        await self._redis.hset(key, mapping={k: str(v) for k, v in mapping.items()})
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def clear_session(self, user_id: str) -> None:
        await self._redis.delete(self._key_session(user_id))

    async def blacklist_token(self, jti: str, ttl_seconds: int | float | None = None) -> None:
        key = self._key_blacklist(jti)
        await self._redis.set(key, "1")
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def is_token_blacklisted(self, jti: str) -> bool:
        return bool(await self._redis.exists(self._key_blacklist(jti)))

    async def store_telemetry_snapshot(
        self,
        vehicle_id: str,
        snapshot: dict[str, Any],
        ttl_seconds: int | float | None = None,
    ) -> None:
        key = self._key_telemetry(vehicle_id)
        await self._redis.set(key, orjson.dumps(snapshot))
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def get_telemetry_snapshot(self, vehicle_id: str) -> dict[str, Any] | None:
        data = await self._redis.get(self._key_telemetry(vehicle_id))
        if data is None:
            return None
        return _orjson_loads_redis_value(data)

    async def set_vehicle_status(self, vehicle_id: str, status: str, ttl_seconds: int | float | None = None) -> None:
        key = self._key_vehicle_status(vehicle_id)
        await self._redis.set(key, status)
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def get_vehicle_status(self, vehicle_id: str) -> str | None:
        return await self._redis.get(self._key_vehicle_status(vehicle_id))

    async def set_heartbeat(self, vehicle_id: str, timestamp: str, ttl_seconds: int | float | None = None) -> None:
        key = self._key_heartbeat(vehicle_id)
        await self._redis.set(key, timestamp)
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def allow_rate_limit(self, client_id: str, limit: int, window_seconds: int) -> bool:
        key = self._key_rate_limit(client_id)
        now_ms = await self._redis.time()
        now_score = float(now_ms[0]) + (float(now_ms[1]) / 1_000_000.0)
        cutoff = now_score - float(window_seconds)
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        _, count = await pipe.execute()
        if int(count) >= limit:
            return False
        member = f"{now_score}:{uuid.uuid4().hex}"
        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now_score})
        pipe.expire(key, int(window_seconds))
        await pipe.execute()
        return True

    async def set_command_state(self, command_id: str, mapping: dict[str, Any], ttl_seconds: int | float | None = None) -> None:
        key = self._key_command_state(command_id)
        await self._redis.set(key, orjson.dumps(mapping))
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def update_command_state(
        self,
        command_id: str,
        mapping: dict[str, Any],
        ttl_seconds: int | float | None = None,
    ) -> None:
        key = self._key_command_state(command_id)
        current = await self.get_command_state(command_id) or {}
        current.update(mapping)
        await self._redis.set(key, orjson.dumps(current))
        if ttl_seconds is not None:
            await self._redis.expire(key, int(ttl_seconds))

    async def get_command_state(self, command_id: str) -> dict[str, Any] | None:
        data = await self._redis.get(self._key_command_state(command_id))
        if data is None:
            return None
        return _orjson_loads_redis_value(data)

    async def append_audit_event(self, record: dict[str, Any]) -> str:
        event_id = uuid.uuid4().hex
        payload = {"id": event_id, **record}
        key = "aero:audit:stream"
        await self._redis.xadd(key, {k: str(v) for k, v in payload.items()}, maxlen=10000, approximate=True)
        return event_id


_runtime_cache = RedisRuntimeCache()


def get_runtime_cache() -> RedisRuntimeCache:
    return _runtime_cache
