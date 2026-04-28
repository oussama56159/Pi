"""Command & control schemas – maps to MAVLink commands."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

__all__ = [
    "CommandType",
    "CommandStatus",
    "CommandRequest",
    "CommandResponse",
    "CommandAck",
    "MAVLinkCommand",
]


class CommandType(str, enum.Enum):
    ARM = "arm"
    DISARM = "disarm"
    TAKEOFF = "takeoff"
    LAND = "land"
    RTL = "rtl"
    HOLD = "hold"
    EMERGENCY_STOP = "emergency_stop"
    SET_MODE = "set_mode"
    SET_SPEED = "set_speed"
    SET_ALTITUDE = "set_altitude"
    GOTO = "goto"
    REBOOT = "reboot"
    SET_PARAMETER = "set_parameter"
    MISSION_START = "mission_start"
    MISSION_PAUSE = "mission_pause"
    MISSION_RESUME = "mission_resume"


class CommandStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CommandRequest(BaseModel):
    """Command from dashboard → API → MQTT → edge agent."""
    vehicle_id: UUID
    command: CommandType
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)
    params: dict = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=10, description="0=normal, 10=critical")
    timeout_seconds: int = Field(default=30, ge=5, le=300)


class CommandResponse(BaseModel):
    id: UUID
    vehicle_id: UUID
    command: CommandType
    idempotency_key: str
    status: CommandStatus
    params: dict
    issued_by: UUID  # user_id
    issued_at: datetime
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class CommandAck(BaseModel):
    """
    Acknowledgment from edge agent → MQTT → cloud.
    Published to: aerocommand/{org}/command/{vehicle_id}/ack
    """
    command_id: str
    vehicle_id: str
    status: CommandStatus
    result_code: int = 0  # MAV_RESULT enum
    message: str | None = None
    timestamp: datetime


class MAVLinkCommand(BaseModel):
    """
    Internal representation of a MAVLink command to be sent to Pixhawk.
    Used by the edge agent to translate CommandRequest → MAVLink.
    """
    command_id: int  # MAV_CMD enum value
    target_system: int = 1
    target_component: int = 1
    param1: float = 0
    param2: float = 0
    param3: float = 0
    param4: float = 0
    param5: float = 0  # x / lat
    param6: float = 0  # y / lng
    param7: float = 0  # z / alt
    confirmation: int = 0

    # Mapping from CommandType to MAV_CMD
    COMMAND_MAP: ClassVar[dict[str, int]] = {
        "arm": 400,           # MAV_CMD_COMPONENT_ARM_DISARM
        "disarm": 400,
        "takeoff": 22,        # MAV_CMD_NAV_TAKEOFF
        "land": 21,           # MAV_CMD_NAV_LAND
        "rtl": 20,            # MAV_CMD_NAV_RETURN_TO_LAUNCH
        "hold": 17,           # MAV_CMD_NAV_LOITER_UNLIM
        "emergency_stop": 400,
        "set_mode": 176,      # MAV_CMD_DO_SET_MODE
        "reboot": 246,        # MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
        "goto": 192,          # MAV_CMD_DO_REPOSITION
        "mission_start": 300,   # MAV_CMD_MISSION_START
        "mission_pause": 193,   # MAV_CMD_DO_PAUSE_CONTINUE (param1=0)
        "mission_resume": 193,  # MAV_CMD_DO_PAUSE_CONTINUE (param1=1)
    }

    model_config = {"json_schema_extra": {"examples": [{"command_id": 400, "param1": 1, "param7": 0}]}}

