"""Telemetry data schemas – maps to MAVLink message fields."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

__all__ = [
    "TelemetryFrame",
    "AttitudeData",
    "GPSData",
    "BatteryData",
    "RCChannels",
    "SystemStatus",
    "TelemetrySnapshot",
    "TelemetryHistoryQuery",
    "TelemetryHistoryResponse",
]


class AttitudeData(BaseModel):
    """Maps to MAVLink ATTITUDE (#30)."""
    roll: float = Field(description="Roll angle in degrees")
    pitch: float = Field(description="Pitch angle in degrees")
    yaw: float = Field(description="Yaw angle in degrees")
    rollspeed: float | None = None
    pitchspeed: float | None = None
    yawspeed: float | None = None


class GPSData(BaseModel):
    """Maps to MAVLink GPS_RAW_INT (#24) + GLOBAL_POSITION_INT (#33)."""
    lat: float
    lng: float
    alt: float  # MSL altitude in meters
    relative_alt: float | None = None
    # MAVLink GPS_FIX_TYPE enum ranges 0..8 (incl. 6=static, 7=PPP, 8=RTK fixed).
    fix_type: int = Field(ge=0, le=8, description="MAVLink GPS fix type (0..8)")
    satellites_visible: int = 0
    hdop: float | None = None
    vdop: float | None = None


class BatteryData(BaseModel):
    """Maps to MAVLink BATTERY_STATUS (#147) + SYS_STATUS (#1)."""
    voltage: float = Field(description="Battery voltage in volts")
    current: float = Field(description="Battery current in amps")
    remaining: float = Field(ge=0, le=100, description="Battery remaining percentage")
    temperature: float | None = Field(default=None, description="Battery temp in °C")
    cell_voltages: list[float] | None = None
    capacity_consumed: int | None = Field(default=None, description="mAh consumed")


class RCChannels(BaseModel):
    """Maps to MAVLink RC_CHANNELS (#65)."""
    channel_count: int = 0
    channels: list[int] = Field(default_factory=list, description="RC channel values (PWM)")
    rssi: int | None = Field(default=None, ge=0, le=255)


class SystemStatus(BaseModel):
    """Maps to MAVLink SYS_STATUS (#1) + HEARTBEAT (#0)."""
    mode: str  # PX4/ArduPilot flight mode string
    armed: bool
    system_status: int  # MAV_STATE enum
    autopilot: str  # "px4" | "ardupilot"
    vehicle_type: int  # MAV_TYPE enum
    cpu_load: float | None = None
    errors_count: int = 0


class TelemetryFrame(BaseModel):
    """
    Complete telemetry frame from a single vehicle.
    Published to MQTT: aerocommand/{org_id}/telemetry/{vehicle_id}/raw
    """
    vehicle_id: str
    timestamp: datetime
    seq: int = Field(description="Sequence number for ordering")

    # Core flight data
    attitude: AttitudeData
    gps: GPSData
    battery: BatteryData
    system: SystemStatus

    # Derived / computed
    airspeed: float = 0.0
    groundspeed: float = 0.0
    heading: float = Field(ge=0, lt=360)
    climb_rate: float = 0.0
    throttle: float = Field(ge=0, le=100)

    # Preferred altitude for UI (typically relative/home altitude). When provided,
    # the dashboard should use this over GPS MSL altitude.
    altitude: float | None = None

    # Optional subsystems
    rc: RCChannels | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None


class TelemetrySnapshot(BaseModel):
    """Cached latest telemetry for a vehicle (stored in Redis)."""
    vehicle_id: str
    timestamp: datetime
    lat: float
    lng: float
    alt: float
    heading: float
    groundspeed: float
    battery: float
    temperature: float | None = None
    mode: str
    armed: bool
    satellites: int
    gps_fix: int


class TelemetryHistoryQuery(BaseModel):
    vehicle_id: str
    start_time: datetime
    end_time: datetime
    resolution: str = Field(default="1s", pattern="^[0-9]+(s|m|h)$")
    fields: list[str] | None = None


class TelemetryHistoryResponse(BaseModel):
    vehicle_id: str
    start_time: datetime
    end_time: datetime
    resolution: str
    points: list[dict]
    total_points: int

