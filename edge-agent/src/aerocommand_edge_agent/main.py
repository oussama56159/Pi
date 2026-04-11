from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from uuid import uuid4

import orjson
from pymavlink import mavutil

from backend.shared.schemas.mission import MissionDownloadRequestEvent, MissionUploadEvent
from backend.shared.schemas.command import CommandAck, CommandStatus, MAVLinkCommand

from .config import EdgeAgentSettings, get_settings
from .mavlink_reader import MavlinkReader
from .mission_downloader import download_mission_from_autopilot
from .mission_uploader import upload_mission_event_to_autopilot
from .mqtt_bridge import MqttBridge
from .telemetry_state import TelemetryState


def _deg(rad: float) -> float:
    return rad * 180.0 / math.pi


def _command_status_from_mav_result(result: int) -> CommandStatus:
    # MAV_RESULT enum (common values):
    # 0 ACCEPTED, 1 TEMPORARILY_REJECTED, 2 DENIED, 3 UNSUPPORTED, 4 FAILED, 5 IN_PROGRESS, 6 CANCELLED
    if result == 0:
        return CommandStatus.ACCEPTED
    if result == 5:
        return CommandStatus.IN_PROGRESS
    if result in (1, 2, 3, 6):
        return CommandStatus.REJECTED
    return CommandStatus.FAILED


async def _mavlink_loop(reader: MavlinkReader, state: TelemetryState, settings: EdgeAgentSettings) -> None:
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

            # Best-effort flight mode decoding.
            # `pymavlink` maintains a human-readable `flightmode` on the mavutil connection
            # after parsing HEARTBEAT/custom_mode. Use it when available.
            flightmode = getattr(reader.master, "flightmode", None)
            if isinstance(flightmode, str) and flightmode.strip():
                state.system.mode = flightmode.strip()
            else:
                # Fallback: preserve prior mode if present, else derive a stable placeholder.
                if not (isinstance(state.system.mode, str) and state.system.mode.strip() and state.system.mode != "UNKNOWN"):
                    custom_mode = msg.data.get("custom_mode")
                    if custom_mode is not None:
                        state.system.mode = f"CUSTOM_MODE_{custom_mode}"

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
            # BATTERY_STATUS voltages are per-cell mV (65535 = unknown), current_battery is 10mA
            if msg.name == "SYS_STATUS":
                if "voltage_battery" in msg.data:
                    state.battery.voltage = float(msg.data.get("voltage_battery", 0)) / 1000.0
                if "current_battery" in msg.data:
                    state.battery.current = float(msg.data.get("current_battery", 0)) / 100.0
            else:
                if "voltages" in msg.data and isinstance(msg.data.get("voltages"), list):
                    raw_cells = msg.data.get("voltages") or []
                    cells_mv = [int(v) for v in raw_cells if isinstance(v, (int, float)) and int(v) not in (0, 65535)]
                    if cells_mv:
                        state.battery.voltage = sum(cells_mv) / 1000.0
                        state.battery.cell_voltages = [v / 1000.0 for v in cells_mv]
                if "current_battery" in msg.data:
                    state.battery.current = float(msg.data.get("current_battery", 0)) / 100.0

            if "battery_remaining" in msg.data:
                # SYS_STATUS.battery_remaining can be -1 when unknown.
                remaining = float(msg.data.get("battery_remaining", 0) or 0)
                if 0.0 <= remaining <= 100.0:
                    # Some firmwares report 0 when unknown; if we have voltage thresholds
                    # and voltage indicates we're not empty, don't lock in 0% as "known".
                    if (
                        remaining == 0.0
                        and not state.battery_remaining_known
                        and settings.BATTERY_VOLTAGE_EMPTY is not None
                        and float(state.battery.voltage or 0.0) > float(settings.BATTERY_VOLTAGE_EMPTY) + 0.1
                    ):
                        pass
                    else:
                        state.battery.remaining = remaining
                        state.battery_remaining_known = True
            if "temperature" in msg.data:
                raw_temperature = float(msg.data.get("temperature", 0))
                if raw_temperature not in (-32768, 32767):
                    state.battery.temperature = raw_temperature / 100.0

            # Fallback: estimate percent from voltage if the autopilot doesn't provide it.
            if not state.battery_remaining_known:
                v_empty = settings.BATTERY_VOLTAGE_EMPTY
                v_full = settings.BATTERY_VOLTAGE_FULL
                if isinstance(v_empty, (int, float)) and isinstance(v_full, (int, float)) and v_full > v_empty:
                    v = float(state.battery.voltage or 0.0)
                    if v > 0:
                        pct = (v - float(v_empty)) / (float(v_full) - float(v_empty)) * 100.0
                        if pct < 0:
                            pct = 0.0
                        elif pct > 100:
                            pct = 100.0
                        state.battery.remaining = pct

        elif msg.name == "STATUSTEXT":
            # Autopilot textual status messages (includes arming/disarming reasons).
            # Common fields: severity (0..7), text.
            text = msg.data.get("text")
            if isinstance(text, bytes):
                try:
                    text = text.decode("utf-8", errors="ignore")
                except Exception:
                    text = str(text)
            if not isinstance(text, str):
                text = str(text or "")
            text = text.strip("\x00 ").strip()

            sev = int(msg.data.get("severity", mavutil.mavlink.MAV_SEVERITY_INFO) or mavutil.mavlink.MAV_SEVERITY_INFO)
            if sev <= mavutil.mavlink.MAV_SEVERITY_ERROR:
                level = "critical"
            elif sev == mavutil.mavlink.MAV_SEVERITY_WARNING:
                level = "warning"
            else:
                level = "info"

            # Print to stdout too (useful when you can't run Mission Planner).
            if text:
                print(f"[AUTOPILOT:{level}] {text}")

            # Forward to MQTT/system alerts if queue is available.
            q = getattr(state, "system_alert_queue", None)
            if q is not None and text:
                alert = {
                    "id": str(uuid4()),
                    "vehicle_id": settings.VEHICLE_ID,
                    "severity": level,
                    "message": text,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    "category": "system",
                    "source": "autopilot",
                }
                try:
                    q.put_nowait(alert)
                except Exception:
                    pass


def _try_set_message_interval(reader: MavlinkReader, message_id: int, hz: float) -> None:
    """Best-effort request for a MAVLink message at a fixed rate."""
    if hz <= 0:
        return

    interval_us = int(1_000_000 / hz)
    master = reader.master
    target_system = int(getattr(master, "target_system", 1) or 1)
    target_component = int(getattr(master, "target_component", 1) or 1)

    try:
        master.mav.command_long_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            float(message_id),
            float(interval_us),
            0,
            0,
            0,
            0,
            0,
        )
    except Exception:
        # Some firmwares/links won't support this; telemetry still works via defaults.
        pass


async def _gcs_heartbeat_loop(reader: MavlinkReader, hz: float) -> None:
    """Send a GCS heartbeat so ArduPilot/PX4 doesn't trigger GCS failsafe."""
    if hz <= 0:
        hz = 1.0
    interval_s = 1.0 / hz

    while True:
        try:
            reader.master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0,
                0,
                mavutil.mavlink.MAV_STATE_ACTIVE,
            )
        except Exception:
            # If the link drops, MavlinkReader is configured to autoreconnect.
            pass
        await asyncio.sleep(interval_s)


async def _run() -> None:
    settings = get_settings()

    reader = MavlinkReader(settings.MAVLINK_CONNECTION, settings.MAVLINK_BAUD, settings.MAVLINK_SOURCE_SYSTEM)
    reader.connect()

    # Best-effort: request the key messages we rely on for UI fields.
    # Message IDs: HEARTBEAT=0, SYS_STATUS=1, GPS_RAW_INT=24, ATTITUDE=30,
    # GLOBAL_POSITION_INT=33, BATTERY_STATUS=147, STATUSTEXT=253
    _try_set_message_interval(reader, 1, max(1.0, settings.TELEMETRY_HZ))      # SYS_STATUS
    _try_set_message_interval(reader, 147, 1.0)                                 # BATTERY_STATUS
    _try_set_message_interval(reader, 33, max(1.0, settings.TELEMETRY_HZ))      # GLOBAL_POSITION_INT
    _try_set_message_interval(reader, 30, max(2.0, settings.TELEMETRY_HZ))      # ATTITUDE
    _try_set_message_interval(reader, 253, 1.0)                                  # STATUSTEXT

    system_alert_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    telemetry_state = TelemetryState(vehicle_id=settings.VEHICLE_ID, system_alert_queue=system_alert_queue)

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

    async def on_command_request(payload: bytes, publish_json) -> None:
        """Handle command requests from cloud by sending MAVLink COMMAND_LONG to the autopilot."""
        data = orjson.loads(payload)

        command_id = str(data.get("command_id") or "unknown")
        timeout_s = float(data.get("timeout") or 10)
        if timeout_s <= 0:
            timeout_s = 10.0

        # Publish immediate receipt ACK.
        await publish_json(
            bridge.command_ack_topic,
            CommandAck(
                command_id=command_id,
                vehicle_id=settings.VEHICLE_ID,
                status=CommandStatus.ACKNOWLEDGED,
                result_code=0,
                message="Received by edge agent; sending to autopilot",
                timestamp=datetime.now(tz=timezone.utc),
            ).model_dump(mode="json"),
        )

        mavlink_payload = data.get("mavlink")
        if not isinstance(mavlink_payload, dict):
            await publish_json(
                bridge.command_ack_topic,
                CommandAck(
                    command_id=command_id,
                    vehicle_id=settings.VEHICLE_ID,
                    status=CommandStatus.FAILED,
                    result_code=4,
                    message="Missing MAVLink command payload",
                    timestamp=datetime.now(tz=timezone.utc),
                ).model_dump(mode="json"),
            )
            return

        cmd = MAVLinkCommand.model_validate(mavlink_payload)

        # Prefer the autopilot IDs learned from heartbeat.
        target_system = int(getattr(reader.master, "target_system", 0) or 0) or int(cmd.target_system or 1)
        target_component = int(getattr(reader.master, "target_component", 0) or 0) or int(cmd.target_component or 1)

        # Send COMMAND_LONG.
        reader.master.mav.command_long_send(
            target_system,
            target_component,
            int(cmd.command_id),
            int(cmd.confirmation),
            float(cmd.param1),
            float(cmd.param2),
            float(cmd.param3),
            float(cmd.param4),
            float(cmd.param5),
            float(cmd.param6),
            float(cmd.param7),
        )

        # Wait for COMMAND_ACK for this command.
        try:
            ack_msg = await reader.wait_for(
                "COMMAND_ACK",
                predicate=lambda d: int(d.get("command", 0) or 0) == int(cmd.command_id),
                timeout_s=min(10.0, timeout_s),
            )
            mav_result = int(ack_msg.data.get("result", 4) or 4)
            status = _command_status_from_mav_result(mav_result)
            await publish_json(
                bridge.command_ack_topic,
                CommandAck(
                    command_id=command_id,
                    vehicle_id=settings.VEHICLE_ID,
                    status=status,
                    result_code=mav_result,
                    message=f"Autopilot COMMAND_ACK result={mav_result}",
                    timestamp=datetime.now(tz=timezone.utc),
                ).model_dump(mode="json"),
            )
        except asyncio.TimeoutError:
            await publish_json(
                bridge.command_ack_topic,
                CommandAck(
                    command_id=command_id,
                    vehicle_id=settings.VEHICLE_ID,
                    status=CommandStatus.TIMEOUT,
                    result_code=4,
                    message="Autopilot did not ACK command in time",
                    timestamp=datetime.now(tz=timezone.utc),
                ).model_dump(mode="json"),
            )

    await asyncio.gather(
        _mavlink_loop(reader, telemetry_state, settings),
        _gcs_heartbeat_loop(reader, max(1.0, settings.HEARTBEAT_HZ)),
        bridge.run(
            telemetry_state=telemetry_state,
            telemetry_interval_s=telemetry_interval_s,
            heartbeat_interval_s=heartbeat_interval_s,
            system_alert_queue=system_alert_queue,
            on_command_request=on_command_request,
            on_mission_upload=on_mission_upload,
            on_mission_download_request=on_mission_download_request,
        ),
    )


def main() -> None:
    asyncio.run(_run())
