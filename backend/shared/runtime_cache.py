"""In-process runtime cache for non-authoritative state.

The cache is intentionally ephemeral and must not be treated as a source of truth.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import RLock
import time
import uuid
from typing import Any


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float | None = None


class InMemoryRuntimeCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: dict[str, _CacheEntry] = {}
        self._token_blacklist: dict[str, _CacheEntry] = {}
        self._telemetry_snapshots: dict[str, _CacheEntry] = {}
        self._vehicle_status: dict[str, _CacheEntry] = {}
        self._heartbeats: dict[str, _CacheEntry] = {}
        self._command_state: dict[str, _CacheEntry] = {}
        self._rate_limits: dict[str, deque[float]] = defaultdict(deque)
        self._audit_events: deque[dict[str, Any]] = deque(maxlen=10_000)

    def _now(self) -> float:
        return time.monotonic()

    def _expiry(self, ttl_seconds: int | float | None) -> float | None:
        if ttl_seconds is None:
            return None
        return self._now() + float(ttl_seconds)

    def _purge_expired(self, store: dict[str, _CacheEntry]) -> None:
        now = self._now()
        expired = [key for key, entry in store.items() if entry.expires_at is not None and entry.expires_at <= now]
        for key in expired:
            store.pop(key, None)

    def set_session(self, user_id: str, mapping: dict[str, Any], ttl_seconds: int | float | None = None) -> None:
        with self._lock:
            self._sessions[user_id] = _CacheEntry(dict(mapping), self._expiry(ttl_seconds))

    def clear_session(self, user_id: str) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)

    def blacklist_token(self, jti: str, ttl_seconds: int | float | None = None) -> None:
        with self._lock:
            self._token_blacklist[jti] = _CacheEntry(True, self._expiry(ttl_seconds))

    def is_token_blacklisted(self, jti: str) -> bool:
        with self._lock:
            self._purge_expired(self._token_blacklist)
            return jti in self._token_blacklist

    def store_telemetry_snapshot(
        self,
        vehicle_id: str,
        snapshot: dict[str, Any],
        ttl_seconds: int | float | None = None,
    ) -> None:
        with self._lock:
            self._telemetry_snapshots[vehicle_id] = _CacheEntry(dict(snapshot), self._expiry(ttl_seconds))

    def get_telemetry_snapshot(self, vehicle_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired(self._telemetry_snapshots)
            entry = self._telemetry_snapshots.get(vehicle_id)
            if not entry:
                return None
            return dict(entry.value)

    def set_vehicle_status(self, vehicle_id: str, status: str, ttl_seconds: int | float | None = None) -> None:
        with self._lock:
            self._vehicle_status[vehicle_id] = _CacheEntry(status, self._expiry(ttl_seconds))

    def get_vehicle_status(self, vehicle_id: str) -> str | None:
        with self._lock:
            self._purge_expired(self._vehicle_status)
            entry = self._vehicle_status.get(vehicle_id)
            return None if entry is None else str(entry.value)

    def set_heartbeat(self, vehicle_id: str, timestamp: str, ttl_seconds: int | float | None = None) -> None:
        with self._lock:
            self._heartbeats[vehicle_id] = _CacheEntry(timestamp, self._expiry(ttl_seconds))

    def allow_rate_limit(self, client_id: str, limit: int, window_seconds: int) -> bool:
        now = self._now()
        cutoff = now - float(window_seconds)
        with self._lock:
            bucket = self._rate_limits[client_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def set_command_state(self, command_id: str, mapping: dict[str, Any], ttl_seconds: int | float | None = None) -> None:
        with self._lock:
            self._command_state[command_id] = _CacheEntry(dict(mapping), self._expiry(ttl_seconds))

    def update_command_state(
        self,
        command_id: str,
        mapping: dict[str, Any],
        ttl_seconds: int | float | None = None,
    ) -> None:
        with self._lock:
            self._purge_expired(self._command_state)
            current = self._command_state.get(command_id)
            if current is None:
                self._command_state[command_id] = _CacheEntry(dict(mapping), self._expiry(ttl_seconds))
                return
            current.value.update(mapping)
            if ttl_seconds is not None:
                current.expires_at = self._expiry(ttl_seconds)

    def get_command_state(self, command_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._purge_expired(self._command_state)
            entry = self._command_state.get(command_id)
            if not entry:
                return None
            return dict(entry.value)

    def append_audit_event(self, record: dict[str, Any]) -> str:
        event_id = uuid.uuid4().hex
        payload = {"id": event_id, **record}
        with self._lock:
            self._audit_events.append(payload)
        return event_id


_runtime_cache = InMemoryRuntimeCache()


def get_runtime_cache() -> InMemoryRuntimeCache:
    return _runtime_cache
