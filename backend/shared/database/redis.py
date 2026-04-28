"""Redis runtime client helpers."""
from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis

from backend.shared.config import get_base_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_base_settings()
    password = settings.REDIS_PASSWORD
    auth_segment = f":{password}@" if password else ""
    dsn = f"redis://{auth_segment}{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
    return Redis.from_url(
        dsn,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )

