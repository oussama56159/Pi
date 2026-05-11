from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time

from backend.shared.schemas.telemetry import (
    AttitudeData,
    BatteryData,
    GPSData,
    SystemStatus,
    TelemetryFrame,
)


@dataclass
class TelemetryState:
    vehicle_id: str
    seq: int = 0

    attitude: AttitudeData = field(default_factory=lambda: AttitudeData(roll=0, pitch=0, yaw=0))
    gps: GPSData = field(
        default_factory=lambda: GPSData(lat=0, lng=0, alt=0, relative_alt=0, fix_type=0, satellites_visible=0)
    )
    battery: BatteryData = field(default_factory=lambda: BatteryData(voltage=0, current=0, remaining=0))
    battery_remaining_known: bool = False
    system: SystemStatus = field(
        default_factory=lambda: SystemStatus(mode="UNKNOWN", armed=False, system_status=0, autopilot="unknown", vehicle_type=0)
    )

    # Optional outbox for system messages (e.g., MAVLink STATUSTEXT).
    system_alert_queue: asyncio.Queue | None = None

    # Connection/health timestamps (monotonic seconds)
    last_mavlink_msg_at: float | None = None
    last_autopilot_heartbeat_at: float | None = None

    # Rolling buffer of recent telemetry frames (last 60 seconds)
    _recent_frames: deque[tuple[float, dict]] = field(default_factory=deque, repr=False)

    heading: float = 0.0
    groundspeed: float = 0.0
    airspeed: float = 0.0
    climb_rate: float = 0.0
    throttle: float = 0.0

    def record_frame(self, frame: TelemetryFrame, *, window_s: float = 60.0) -> None:
        """Store a rolling history of frames for post-incident debugging."""
        now = time.monotonic()
        try:
            payload = frame.model_dump(mode="json")
        except Exception:
            return

        self._recent_frames.append((now, payload))

        cutoff = now - float(window_s)
        while self._recent_frames and self._recent_frames[0][0] < cutoff:
            self._recent_frames.popleft()

    def get_recent_frames(self) -> list[dict]:
        """Return buffered frames as plain JSON-serializable dicts."""
        return [payload for (_t, payload) in list(self._recent_frames)]

    def to_frame(self) -> TelemetryFrame:
        self.seq += 1

        altitude = self.gps.relative_alt if self.gps.relative_alt is not None else self.gps.alt
        # When sitting indoors/on the ground, baro/home offsets can yield small negative
        # relative altitudes; clamp small negatives so the UI doesn't show confusing values.
        if altitude is not None and altitude < 0:
            stationary = (self.groundspeed < 0.2) and (abs(self.climb_rate) < 0.2)
            if stationary and altitude > -5.0:
                altitude = 0.0

        return TelemetryFrame(
            vehicle_id=self.vehicle_id,
            timestamp=datetime.now(tz=timezone.utc),
            seq=self.seq,
            attitude=self.attitude,
            gps=self.gps,
            battery=self.battery,
            system=self.system,
            airspeed=self.airspeed,
            groundspeed=self.groundspeed,
            heading=self.heading % 360,
            climb_rate=self.climb_rate,
            throttle=max(0, min(100, self.throttle)),
            altitude=altitude,
            rc=None,
            wind_speed=None,
            wind_direction=None,
        )
