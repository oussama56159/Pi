from __future__ import annotations

import pytest

from backend.services.telemetry import service as telemetry_service
from backend.services.command import service as command_service
from backend.shared.retry import retry_async
from backend.shared.schemas.command import CommandStatus


class _FakeTelemetryCache:
    def __init__(self) -> None:
        self.heartbeat_calls = []
        self.status_calls = []

    async def set_heartbeat(self, vehicle_id: str, ts: str, ttl_seconds: int):
        self.heartbeat_calls.append((vehicle_id, ts, ttl_seconds))

    async def set_vehicle_status(self, vehicle_id: str, status: str, ttl_seconds: int):
        self.status_calls.append((vehicle_id, status, ttl_seconds))


class _FakeCommandCache:
    def __init__(self) -> None:
        self.updated = []
        self.state = {"status": CommandStatus.SENT.value}

    async def get_command_state(self, _command_id: str):
        return self.state

    async def update_command_state(self, command_id: str, mapping: dict):
        self.updated.append((command_id, mapping))
        self.state.update(mapping)


@pytest.mark.asyncio
async def test_process_heartbeat_updates_distributed_status(monkeypatch):
    fake_cache = _FakeTelemetryCache()
    monkeypatch.setattr(telemetry_service, "get_runtime_cache", lambda: fake_cache)

    async def _noop(_vehicle_id: str):
        return None

    monkeypatch.setattr(telemetry_service, "_sync_vehicle_online_state", _noop)
    await telemetry_service.process_heartbeat("veh-1", {"connected": True})
    assert fake_cache.heartbeat_calls
    assert fake_cache.status_calls[0][1] == "online"


@pytest.mark.asyncio
async def test_retry_async_recovers_after_transient_failures():
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await retry_async(flaky, retries=4, base_delay_s=0.001, max_delay_s=0.01, retry_on=(RuntimeError,))
    assert result == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_command_timeout_marks_state(monkeypatch):
    fake_cache = _FakeCommandCache()
    monkeypatch.setattr(command_service, "get_runtime_cache", lambda: fake_cache)

    async def _fast_sleep(_timeout: int):
        return None

    monkeypatch.setattr(command_service.asyncio, "sleep", _fast_sleep)
    await command_service._command_timeout_watcher("cmd-timeout", timeout=5)
    assert fake_cache.updated
    assert fake_cache.updated[0][1]["status"] == CommandStatus.TIMEOUT.value

