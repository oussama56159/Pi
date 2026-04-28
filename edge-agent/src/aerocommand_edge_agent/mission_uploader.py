from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from backend.shared.mqtt_topics import MQTTTopics
from backend.shared.schemas.mission import (
    MissionStatus,
    MissionStatusEvent,
    MissionUploadEvent,
    MissionProgressEvent,
    waypoint_command_to_mav_cmd,
)

from .mavlink_reader import MavlinkReader

logger = logging.getLogger(__name__)


async def upload_mission_event_to_autopilot(
    *,
    reader: MavlinkReader,
    event: MissionUploadEvent,
    publish_json: Callable[[str, dict], Awaitable[None]],
    request_timeout_s: float = 30.0,
    max_retries: int = 3,
) -> None:
    """Upload the mission contained in a MissionUploadEvent to the connected autopilot.

    This implements the MAVLink mission upload handshake (COUNT/REQUEST/ITEM/ACK).

    Notes:
    - This currently uses the autopilot's request messages (MISSION_REQUEST_INT preferred).
    - Mission status/progress is published back to MQTT so the cloud can persist it.
    """

    org_id = str(event.org_id)
    vehicle_id = str(event.vehicle_id)
    mission_id = str(event.mission.id)

    status_topic = MQTTTopics.mission_status(org_id, vehicle_id)
    progress_topic = MQTTTopics.mission_progress(org_id, vehicle_id)

    def now() -> datetime:
        return datetime.now(tz=timezone.utc)

    async def publish_status(status: MissionStatus, message: str | None = None, *, progress: float | None = None) -> None:
        payload = MissionStatusEvent(
            request_id=event.request_id,
            org_id=org_id,
            vehicle_id=vehicle_id,
            mission_id=mission_id,
            status=status,
            message=message,
            progress=progress,
            timestamp=now(),
        ).model_dump(mode="json")
        await publish_json(status_topic, payload)

    async def publish_progress(current_waypoint: int, total_waypoints: int, status: MissionStatus) -> None:
        pct = 0.0 if total_waypoints <= 0 else (current_waypoint / total_waypoints) * 100.0
        payload = MissionProgressEvent(
            vehicle_id=vehicle_id,
            mission_id=mission_id,
            current_waypoint=current_waypoint,
            total_waypoints=total_waypoints,
            progress=max(0.0, min(100.0, pct)),
            status=status,
            timestamp=now(),
        ).model_dump(mode="json")
        await publish_json(progress_topic, payload)

    waypoints = sorted(event.mission.waypoints, key=lambda w: int(w.seq))
    if not waypoints:
        await publish_status(MissionStatus.FAILED, "Mission has no waypoints")
        return

    master = reader.master
    target_system = int(getattr(master, "target_system", 1) or 1)
    target_component = int(getattr(master, "target_component", 1) or 1)

    wp_by_seq = {int(w.seq): w for w in waypoints}
    count = len(waypoints)

    await publish_status(MissionStatus.UPLOADING, f"Uploading {count} mission items")

    # Clear existing mission (best-effort; not all firmwares require this).
    try:
        try:
            master.mav.mission_clear_all_send(target_system, target_component, 0)
        except TypeError:
            master.mav.mission_clear_all_send(target_system, target_component)
    except Exception as exc:
        logger.info("MISSION_CLEAR_ALL send failed (continuing): %s", exc)

    for attempt in range(1, max_retries + 1):
        sent: set[int] = set()
        try:
            try:
                master.mav.mission_count_send(target_system, target_component, count, 0)
            except TypeError:
                master.mav.mission_count_send(target_system, target_component, count)
        except Exception as exc:
            await publish_status(MissionStatus.FAILED, f"Failed to send MISSION_COUNT: {exc}")
            return

        try:
            while len(sent) < count:
                req = await reader.wait_for(
                    ("MISSION_REQUEST_INT", "MISSION_REQUEST"),
                    predicate=lambda d: (
                        (d.get("seq") is not None)
                        and (int(d.get("seq")) in wp_by_seq)
                        and (int(d.get("seq")) not in sent)
                    ),
                    timeout_s=request_timeout_s,
                )

                seq = int(req.data.get("seq"))
                wp = wp_by_seq[seq]

                mav_cmd = waypoint_command_to_mav_cmd(wp.command)
                frame = int(getattr(wp, "frame", 3) or 3)

                current = 1 if seq == 0 else 0
                autocontinue = 1

                if req.name == "MISSION_REQUEST_INT":
                    x = int(float(wp.lat) * 1e7)
                    y = int(float(wp.lng) * 1e7)
                    z = float(wp.alt)
                    try:
                        try:
                            master.mav.mission_item_int_send(
                                target_system,
                                target_component,
                                seq,
                                frame,
                                mav_cmd,
                                current,
                                autocontinue,
                                float(wp.param1),
                                float(wp.param2),
                                float(wp.param3),
                                float(wp.param4),
                                x,
                                y,
                                z,
                                0,
                            )
                        except TypeError:
                            master.mav.mission_item_int_send(
                                target_system,
                                target_component,
                                seq,
                                frame,
                                mav_cmd,
                                current,
                                autocontinue,
                                float(wp.param1),
                                float(wp.param2),
                                float(wp.param3),
                                float(wp.param4),
                                x,
                                y,
                                z,
                            )
                    except Exception as exc:
                        await publish_status(MissionStatus.FAILED, f"Failed to send MISSION_ITEM_INT seq={seq}: {exc}")
                        return
                else:
                    x = float(wp.lat)
                    y = float(wp.lng)
                    z = float(wp.alt)
                    try:
                        try:
                            master.mav.mission_item_send(
                                target_system,
                                target_component,
                                seq,
                                frame,
                                mav_cmd,
                                current,
                                autocontinue,
                                float(wp.param1),
                                float(wp.param2),
                                float(wp.param3),
                                float(wp.param4),
                                x,
                                y,
                                z,
                                0,
                            )
                        except TypeError:
                            master.mav.mission_item_send(
                                target_system,
                                target_component,
                                seq,
                                frame,
                                mav_cmd,
                                current,
                                autocontinue,
                                float(wp.param1),
                                float(wp.param2),
                                float(wp.param3),
                                float(wp.param4),
                                x,
                                y,
                                z,
                            )
                    except Exception as exc:
                        await publish_status(MissionStatus.FAILED, f"Failed to send MISSION_ITEM seq={seq}: {exc}")
                        return

                sent.add(seq)
                await publish_progress(len(sent), count, MissionStatus.UPLOADING)

            ack = await reader.wait_for("MISSION_ACK", timeout_s=request_timeout_s)
            ack_type = ack.data.get("type")
            accepted = (ack_type is None) or int(ack_type) == 0

            if accepted:
                await publish_status(MissionStatus.UPLOADED, "Mission upload accepted", progress=100.0)
                return
            await publish_status(MissionStatus.FAILED, f"Mission upload rejected (ACK type={ack_type})")
            return
        except asyncio.TimeoutError:
            if attempt >= max_retries:
                await publish_status(MissionStatus.FAILED, "Mission upload timed out waiting for autopilot")
                return
            await publish_status(
                MissionStatus.UPLOADING,
                f"Upload timeout, retrying ({attempt}/{max_retries}) from partial state",
            )
            await asyncio.sleep(min(2.0 * attempt, 5.0))
