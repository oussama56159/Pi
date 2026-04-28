from __future__ import annotations

import pytest

from backend.services.command import service as command_service
from backend.shared.schemas.command import CommandAck, CommandStatus


class _FakeCache:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []
        self.state = {"status": CommandStatus.SENT.value}

    async def update_command_state(self, command_id: str, mapping: dict) -> None:
        self.updated.append((command_id, mapping))
        self.state.update(mapping)

    async def get_command_state(self, command_id: str):
        return self.state


@pytest.mark.asyncio
async def test_handle_command_ack_updates_runtime_state(monkeypatch):
    cache = _FakeCache()
    monkeypatch.setattr(command_service, "get_runtime_cache", lambda: cache)
    ack = CommandAck(
        command_id="cmd-1",
        vehicle_id="veh-1",
        status=CommandStatus.ACCEPTED,
        result_code=0,
        message="ok",
        timestamp="2026-01-01T00:00:00Z",
    )

    await command_service.handle_command_ack(ack)

    assert cache.updated
    assert cache.updated[0][0] == "cmd-1"
    assert cache.updated[0][1]["status"] == CommandStatus.ACCEPTED.value

