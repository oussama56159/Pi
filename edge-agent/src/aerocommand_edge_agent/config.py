from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class EdgeAgentSettings(BaseSettings):
    # Identity
    ORG_ID: str = Field(min_length=1)
    VEHICLE_ID: str = Field(min_length=1)

    # MAVLink
    MAVLINK_CONNECTION: str = Field(
        default="udp:127.0.0.1:14550",
        description="pymavlink connection string, e.g. /dev/ttyAMA0 or udp:0.0.0.0:14550",
    )
    MAVLINK_BAUD: int = 57600
    MAVLINK_SOURCE_SYSTEM: int = 255

    # MQTT
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None
    MQTT_CLIENT_ID: str = "aerocommand-edge"
    MQTT_KEEPALIVE: int = 60
    MQTT_QOS: int = Field(default=1, ge=0, le=2)

    # Publishing cadence
    TELEMETRY_HZ: float = Field(default=2.0, gt=0)
    HEARTBEAT_HZ: float = Field(default=1.0, gt=0)

    # Battery (optional)
    # If the autopilot doesn't report battery remaining percent (-1/unknown),
    # the agent can estimate it linearly from pack voltage.
    BATTERY_VOLTAGE_EMPTY: float | None = Field(default=None, gt=0)
    BATTERY_VOLTAGE_FULL: float | None = Field(default=None, gt=0)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


def get_settings() -> EdgeAgentSettings:
    return EdgeAgentSettings()
