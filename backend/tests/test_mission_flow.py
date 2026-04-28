from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.services.mission import service as mission_service


class _FakeMqtt:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, payload):
        self.published.append((topic, payload))


class _FakeDb:
    def __init__(self) -> None:
        self._mission = SimpleNamespace(status=None, vehicle_id=None)

    async def execute(self, *_args, **_kwargs):
        class _R:
            def __init__(self, mission):
                self._mission = mission

            def scalar_one(self):
                return self._mission

        return _R(self._mission)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_upload_mission_publishes_to_mqtt(monkeypatch):
    org_id = uuid4()
    vehicle_id = uuid4()
    mission_id = uuid4()
    fake_mqtt = _FakeMqtt()
    fake_db = _FakeDb()

    async def _fake_get_mission_response(*_args, **_kwargs):
        return SimpleNamespace(id=mission_id, waypoints=[SimpleNamespace(seq=0, lat=1.0, lng=2.0, alt=10.0)])

    monkeypatch.setattr(mission_service, "_get_mission_response", _fake_get_mission_response)
    async def _fake_get_mqtt():
        return fake_mqtt

    monkeypatch.setattr(mission_service, "get_mqtt", _fake_get_mqtt)

    data = SimpleNamespace(mission_id=mission_id, vehicle_id=vehicle_id)
    result = await mission_service.upload_mission_to_vehicle(fake_db, org_id, data, request_id="req-123")

    assert result["status"] == "uploading"
    assert fake_mqtt.published
    assert "mission" in fake_mqtt.published[0][0]

