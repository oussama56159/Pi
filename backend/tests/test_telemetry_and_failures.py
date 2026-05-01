from __future__ import annotations

from uuid import UUID
from types import SimpleNamespace

import pytest

from backend.services.alert import service as alert_service
from backend.services.telemetry import service as telemetry_service
from backend.services.command import service as command_service
from backend.shared.retry import retry_async
from backend.shared.schemas.alert import AlertCategory, AlertSeverity
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


class _FakeAlertResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return None


class _FakeAlertDb:
    def __init__(self, rules, zones):
        self._rules = rules
        self._zones = zones
        self._calls = 0

    async def execute(self, *_args, **_kwargs):
        self._calls += 1
        if self._calls == 1:
            return _FakeAlertResult(self._rules)
        return _FakeAlertResult(self._zones)


class _FakeCommandRow:
    def __init__(self) -> None:
        self.status = CommandStatus.SENT
        self.completed_at = None
        self.error_message = None


class _FakeCommandResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeCommandSession:
    def __init__(self, row) -> None:
        self._row = row
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *_args, **_kwargs):
        return _FakeCommandResult(self._row)

    async def commit(self):
        self.commits += 1


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
async def test_process_telemetry_invokes_alert_evaluation(monkeypatch):
    calls = []

    async def _noop(*_args, **_kwargs):
        return None

    async def _record_alerts(frame):
        calls.append(frame.vehicle_id)

    monkeypatch.setattr(telemetry_service, "_sync_vehicle_state_from_frame", _noop)
    monkeypatch.setattr(telemetry_service, "_store_in_postgres", _noop)
    monkeypatch.setattr(telemetry_service, "_cache_in_memory", _noop)
    monkeypatch.setattr(telemetry_service, "_broadcast_via_websocket", _noop)
    monkeypatch.setattr(telemetry_service, "_evaluate_and_persist_alerts", _record_alerts)

    payload = {
        "vehicle_id": "veh-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "seq": 1,
        "attitude": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "gps": {
            "lat": 1.0,
            "lng": 2.0,
            "alt": 3.0,
            "fix_type": 3,
            "satellites_visible": 7,
        },
        "battery": {"voltage": 12.0, "current": 1.0, "remaining": 55.0},
        "system": {"mode": "GUIDED", "armed": False, "system_status": 4, "autopilot": "px4", "vehicle_type": 2},
        "airspeed": 0.0,
        "groundspeed": 0.0,
        "heading": 0.0,
        "climb_rate": 0.0,
        "throttle": 0.0,
    }

    await telemetry_service.process_telemetry("veh-1", payload)

    assert calls == ["veh-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("cooldown_active, expected_count", [(True, 0), (False, 1)])
async def test_evaluate_telemetry_respects_rule_cooldown(monkeypatch, cooldown_active, expected_count):
    rule = SimpleNamespace(
        id="rule-1",
        condition={"field": "battery.remaining", "operator": "lt", "value": 20},
        severity=AlertSeverity.WARNING,
        category=AlertCategory.BATTERY,
        name="Low battery",
        cooldown_seconds=30,
    )
    telemetry = telemetry_service.TelemetryFrame.model_validate({
        "vehicle_id": "veh-1",
        "timestamp": "2026-01-01T00:00:00Z",
        "seq": 1,
        "attitude": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "gps": {
            "lat": 1.0,
            "lng": 2.0,
            "alt": 3.0,
            "fix_type": 3,
            "satellites_visible": 7,
        },
        "battery": {"voltage": 12.0, "current": 1.0, "remaining": 15.0},
        "system": {"mode": "GUIDED", "armed": False, "system_status": 4, "autopilot": "px4", "vehicle_type": 2},
        "airspeed": 0.0,
        "groundspeed": 0.0,
        "heading": 0.0,
        "climb_rate": 0.0,
        "throttle": 0.0,
    })
    fake_db = _FakeAlertDb([rule], [])

    monkeypatch.setattr(alert_service, "evaluate_condition", lambda *_args, **_kwargs: True)

    async def _cooldown(*_args, **_kwargs):
        return cooldown_active

    monkeypatch.setattr(alert_service, "_rule_alert_in_cooldown", _cooldown)

    alerts = await alert_service.evaluate_telemetry_against_rules(
        fake_db,
        UUID("11111111-1111-1111-1111-111111111111"),
        telemetry,
    )

    assert len(alerts) == expected_count


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
    fake_row = _FakeCommandRow()
    fake_session = _FakeCommandSession(fake_row)
    monkeypatch.setattr(command_service, "get_runtime_cache", lambda: fake_cache)

    async def _fake_get_direct_postgres_session():
        return fake_session

    monkeypatch.setattr(command_service, "get_direct_postgres_session", _fake_get_direct_postgres_session)

    async def _fast_sleep(_timeout: int):
        return None

    monkeypatch.setattr(command_service.asyncio, "sleep", _fast_sleep)
    await command_service._command_timeout_watcher("cmd-timeout", timeout=5)
    assert fake_cache.updated
    assert fake_cache.updated[0][1]["status"] == CommandStatus.TIMEOUT.value
    assert fake_row.status == CommandStatus.TIMEOUT
    assert fake_row.error_message and "timed out" in fake_row.error_message
    assert fake_session.commits == 1

