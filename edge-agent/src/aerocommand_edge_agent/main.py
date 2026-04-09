from __future__ import annotations

import asyncio
import math

import orjson

from backend.shared.schemas.mission import MissionDownloadRequestEvent, MissionUploadEvent

from .config import get_settings
from .mavlink_reader import MavlinkReader
from .mission_downloader import download_mission_from_autopilot
from .mission_uploader import upload_mission_event_to_autopilot
from .mqtt_bridge import MqttBridge
from .telemetry_state import TelemetryState


def _deg(rad: float) -> float:
    return rad * 180.0 / math.pi


async def _mavlink_loop(reader: MavlinkReader, state: TelemetryState) -> None:
    # Run one long-lived blocking reader in a background thread and feed an asyncio.Queue.
    # This avoids scheduling a new `asyncio.to_thread(...)` call per MAVLink packet.
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)

    def _enqueue(m: object) -> None:
        try:
            queue.put_nowait(m)
        except asyncio.QueueFull:
            # Drop when overwhelmed; we publish a low-rate snapshot anyway.
            pass

    def _reader_thread() -> None:
        while True:
            msg = reader.recv(1.0)
            if msg is None:
                continue
            loop.call_soon_threadsafe(_enqueue, msg)

    asyncio.create_task(asyncio.to_thread(_reader_thread))

    while True:
        msg = await queue.get()

        reader.notify(msg)

        if msg.name == "HEARTBEAT":
            base_mode = int(msg.data.get("base_mode", 0))
            armed = bool(base_mode & 0b10000000)  # MAV_MODE_FLAG_SAFETY_ARMED
            state.system.armed = armed
            state.system.system_status = int(msg.data.get("system_status", 0))
            state.system.vehicle_type = int(msg.data.get("type", 0))
            state.system.autopilot = str(msg.data.get("autopilot", "unknown"))

        elif msg.name == "ATTITUDE":
            state.attitude.roll = _deg(float(msg.data.get("roll", 0.0)))
            state.attitude.pitch = _deg(float(msg.data.get("pitch", 0.0)))
            state.attitude.yaw = _deg(float(msg.data.get("yaw", 0.0)))
            state.attitude.rollspeed = float(msg.data.get("rollspeed", 0.0))
            state.attitude.pitchspeed = float(msg.data.get("pitchspeed", 0.0))
            state.attitude.yawspeed = float(msg.data.get("yawspeed", 0.0))
            state.heading = state.attitude.yaw % 360

        elif msg.name in ("GPS_RAW_INT", "GLOBAL_POSITION_INT"):
            # GPS_RAW_INT lat/lon are 1e7 scaled; GLOBAL_POSITION_INT is also 1e7
            if "lat" in msg.data and "lon" in msg.data:
                state.gps.lat = float(msg.data.get("lat", 0)) / 1e7
                state.gps.lng = float(msg.data.get("lon", 0)) / 1e7

            if "alt" in msg.data:
                # GPS_RAW_INT alt is mm; GLOBAL_POSITION_INT alt is mm
                state.gps.alt = float(msg.data.get("alt", 0)) / 1000.0

            if "relative_alt" in msg.data:
                state.gps.relative_alt = float(msg.data.get("relative_alt", 0)) / 1000.0

            if "fix_type" in msg.data:
                # MAVLink GPS_FIX_TYPE is 0..8; keep within expected bounds.
                fix_type = int(msg.data.get("fix_type", 0) or 0)
                if fix_type < 0:
                    fix_type = 0
                elif fix_type > 8:
                    fix_type = 8
                state.gps.fix_type = fix_type

            if "satellites_visible" in msg.data:
                state.gps.satellites_visible = int(msg.data.get("satellites_visible", 0))

            if "vel" in msg.data:
                # GPS_RAW_INT vel is cm/s
                state.groundspeed = float(msg.data.get("vel", 0)) / 100.0

        elif msg.name in ("SYS_STATUS", "BATTERY_STATUS"):
            # SYS_STATUS voltage_battery is mV, current_battery is cA
            if "voltage_battery" in msg.data:
                state.battery.voltage = float(msg.data.get("voltage_battery", 0)) / 1000.0
            if "current_battery" in msg.data:
                state.battery.current = float(msg.data.get("current_battery", 0)) / 100.0
            if "battery_remaining" in msg.data:
                # SYS_STATUS.battery_remaining can be -1 when unknown.
                remaining = float(msg.data.get("battery_remaining", 0) or 0)
                if 0.0 <= remaining <= 100.0:
                    state.battery.remaining = remaining
            if "temperature" in msg.data:
                raw_temperature = float(msg.data.get("temperature", 0))
                if raw_temperature not in (-32768, 32767):
                    state.battery.temperature = raw_temperature / 100.0


async def _run() -> None:
    settings = get_settings()

    reader = MavlinkReader(settings.MAVLINK_CONNECTION, settings.MAVLINK_BAUD, settings.MAVLINK_SOURCE_SYSTEM)
    reader.connect()

    telemetry_state = TelemetryState(vehicle_id=settings.VEHICLE_ID)

    bridge = MqttBridge(
        org_id=settings.ORG_ID,
        vehicle_id=settings.VEHICLE_ID,
        host=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        username=settings.MQTT_USERNAME,
        password=settings.MQTT_PASSWORD,
        client_id=settings.MQTT_CLIENT_ID,
        keepalive=settings.MQTT_KEEPALIVE,
        qos=settings.MQTT_QOS,
    )

    telemetry_interval_s = 1.0 / settings.TELEMETRY_HZ
    heartbeat_interval_s = 1.0 / settings.HEARTBEAT_HZ

    async def on_mission_upload(payload: bytes, publish_json) -> None:
        data = orjson.loads(payload)
        event = MissionUploadEvent.model_validate(data)
        await upload_mission_event_to_autopilot(reader=reader, event=event, publish_json=publish_json)

    async def on_mission_download_request(payload: bytes, publish_json) -> None:
        data = orjson.loads(payload)
        event = MissionDownloadRequestEvent.model_validate(data)

        async def _handle() -> None:
            await download_mission_from_autopilot(reader=reader, event=event, publish_json=publish_json)

        asyncio.create_task(_handle())

    await asyncio.gather(
        _mavlink_loop(reader, telemetry_state),
        bridge.run(
            telemetry_state=telemetry_state,
            telemetry_interval_s=telemetry_interval_s,
            heartbeat_interval_s=heartbeat_interval_s,
            on_mission_upload=on_mission_upload,
            on_mission_download_request=on_mission_download_request,
        ),
    )


def main() -> None:
    asyncio.run(_run())
