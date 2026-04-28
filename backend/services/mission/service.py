"""Mission business logic – CRUD, upload to vehicles via MQTT."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from uuid import uuid4
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.shared.schemas.auth import Role
from backend.shared.schemas.mission import (
    MissionCreate,
    MissionResponse,
    MissionAssignmentResponse,
    MissionStatus,
    MissionStatusUpdateRequest,
    MissionUpdate,
    MissionDownloadRequest,
    MissionUploadRequest,
    MissionDownloadRequestEvent,
    MissionDownloadResponseEvent,
    MissionUploadEvent,
    WaypointResponse,
)
from backend.shared.schemas.mission_graph import (
    CompileResult,
    CompiledWaypoint,
    MissionEdgeType,
    MissionGraph,
    MissionNodeType,
    MissionSeverity,
    ValidationIssue,
    ValidationResult,
)
from backend.shared.mqtt_topics import MQTTTopics
from backend.shared.mqtt_runtime import get_mqtt
from backend.shared.retry import retry_async
from backend.shared.metrics import (
    MISSION_DOWNLOAD_TOTAL,
    MISSION_UPLOAD_TOTAL,
    MQTT_PUBLISH_LATENCY_SECONDS,
)
from backend.services.telemetry.websocket_manager import ws_manager

from backend.services.fleet.models import FleetUserAssignment, Vehicle
from .models import Mission, MissionAssignment, Waypoint

logger = logging.getLogger(__name__)


_MISSION_GRAPH_SETTINGS_KEY = "mission_graph"


_mission_download_listener_started = False
_mission_download_pending: dict[str, asyncio.Future[dict]] = {}


async def _ensure_mission_download_listener() -> None:
    global _mission_download_listener_started
    if _mission_download_listener_started:
        return

    mqtt = await get_mqtt()

    async def _handle(topic: str, payload: dict) -> None:
        request_id = payload.get("request_id")
        if not request_id:
            return
        fut = _mission_download_pending.get(str(request_id))
        if fut is not None and not fut.done():
            fut.set_result(payload)

    await mqtt.subscribe("aerocommand/+/mission/+/download/response", _handle)
    _mission_download_listener_started = True


async def create_mission(
    db: AsyncSession, org_id: UUID, data: MissionCreate, *, user: dict | None = None
) -> MissionResponse:
    mission = Mission(
        name=data.name,
        description=data.description,
        type=data.type,
        vehicle_id=data.vehicle_id,
        organization_id=org_id,
        settings=data.settings,
        total_distance=_calculate_distance(data.waypoints) if data.waypoints else None,
    )
    db.add(mission)
    await db.flush()

    if data.vehicle_id:
        await _assert_vehicle_access(db, org_id, data.vehicle_id, user)
        assignment = MissionAssignment(
            mission_id=mission.id,
            vehicle_id=data.vehicle_id,
            status=MissionStatus.READY,
            assigned_by=UUID(user["user_id"]) if user and user.get("user_id") else None,
            active=True,
        )
        db.add(assignment)

    for wp_data in data.waypoints:
        wp = Waypoint(
            mission_id=mission.id,
            seq=wp_data.seq, lat=wp_data.lat, lng=wp_data.lng, alt=wp_data.alt,
            command=wp_data.command, frame=wp_data.frame,
            param1=wp_data.param1, param2=wp_data.param2,
            param3=wp_data.param3, param4=wp_data.param4,
        )
        db.add(wp)

    await db.flush()
    return await _get_mission_response(db, mission.id, org_id)


async def get_mission(db: AsyncSession, org_id: UUID, mission_id: UUID, *, user: dict | None = None) -> MissionResponse:
    mission = await _get_mission(db, mission_id, org_id)
    await _assert_mission_access(db, org_id, mission, user)
    return _mission_to_response(mission)


async def list_missions(
    db: AsyncSession,
    org_id: UUID,
    vehicle_id: UUID | None = None,
    status: MissionStatus | None = None,
    *,
    user: dict | None = None,
) -> list[MissionResponse]:
    query = select(Mission).where(Mission.organization_id == org_id).options(
        selectinload(Mission.waypoints),
        selectinload(Mission.assignments),
    )
    joined_assignments = False
    if vehicle_id:
        query = query.join(MissionAssignment, MissionAssignment.mission_id == Mission.id)
        query = query.where(
            MissionAssignment.vehicle_id == vehicle_id,
            MissionAssignment.active.is_(True),
        )
        query = query.distinct()
        joined_assignments = True
    if status:
        query = query.where(Mission.status == status)

    allowed_vehicle_ids = await _get_allowed_vehicle_ids(db, org_id, user)
    if allowed_vehicle_ids is not None:
        if not allowed_vehicle_ids:
            return []
        if not joined_assignments:
            query = query.join(MissionAssignment, MissionAssignment.mission_id == Mission.id)
        query = query.where(
            MissionAssignment.active.is_(True),
            MissionAssignment.vehicle_id.in_(allowed_vehicle_ids),
        )
        query = query.distinct()
    result = await db.execute(query.order_by(Mission.created_at.desc()))
    missions = result.scalars().all()
    return [_mission_to_response(m) for m in missions]


async def update_mission(
    db: AsyncSession, org_id: UUID, mission_id: UUID, data: MissionUpdate, *, user: dict | None = None
) -> MissionResponse:
    result = await db.execute(
        select(Mission).where(Mission.id == mission_id, Mission.organization_id == org_id)
        .options(selectinload(Mission.waypoints))
    )
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    await _assert_mission_access(db, org_id, mission, user)
    if mission.status not in (MissionStatus.DRAFT, MissionStatus.READY):
        raise HTTPException(status_code=400, detail="Cannot edit active mission")

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "waypoints" and value is not None:
            # Replace all waypoints
            for wp in mission.waypoints:
                await db.delete(wp)
            for wp_data in data.waypoints:
                wp = Waypoint(
                    mission_id=mission.id, seq=wp_data.seq, lat=wp_data.lat, lng=wp_data.lng,
                    alt=wp_data.alt, command=wp_data.command, frame=wp_data.frame,
                    param1=wp_data.param1, param2=wp_data.param2,
                    param3=wp_data.param3, param4=wp_data.param4,
                )
                db.add(wp)
        elif hasattr(mission, field):
            setattr(mission, field, value)

    await db.flush()
    return await _get_mission_response(db, mission_id, org_id)


async def delete_mission(
    db: AsyncSession, org_id: UUID, mission_id: UUID, *, user: dict | None = None
) -> None:
    mission = await _get_mission(db, mission_id, org_id)
    await _assert_mission_access(db, org_id, mission, user)
    if mission.status not in (MissionStatus.DRAFT, MissionStatus.READY):
        raise HTTPException(status_code=400, detail="Cannot delete active mission")
    await db.delete(mission)


async def assign_mission(
    db: AsyncSession,
    org_id: UUID,
    mission_id: UUID,
    vehicle_ids: list[UUID],
    *,
    assigned_by: str | None = None,
    replace_existing: bool = True,
    user: dict | None = None,
) -> list[MissionAssignmentResponse]:
    mission = await _get_mission(db, mission_id, org_id)

    vehicles = (await db.execute(
        select(Vehicle).where(Vehicle.id.in_(vehicle_ids), Vehicle.organization_id == org_id)
    )).scalars().all()
    if len(vehicles) != len(set(vehicle_ids)):
        raise HTTPException(status_code=404, detail="One or more vehicles not found")

    for vehicle in vehicles:
        await _assert_vehicle_access(db, org_id, vehicle.id, user)

    if replace_existing:
        existing_assignments = (await db.execute(
            select(MissionAssignment).where(
                MissionAssignment.vehicle_id.in_(vehicle_ids),
                MissionAssignment.active.is_(True),
            )
        )).scalars().all()
        for assignment in existing_assignments:
            assignment.active = False

    new_assignments: list[MissionAssignment] = []
    for vehicle_id in vehicle_ids:
        existing = (await db.execute(
            select(MissionAssignment).where(
                MissionAssignment.mission_id == mission_id,
                MissionAssignment.vehicle_id == vehicle_id,
                MissionAssignment.active.is_(True),
            )
        )).scalar_one_or_none()
        if existing:
            continue
        assignment = MissionAssignment(
            mission_id=mission_id,
            vehicle_id=vehicle_id,
            status=MissionStatus.READY,
            assigned_by=UUID(assigned_by) if assigned_by else None,
            active=True,
        )
        db.add(assignment)
        new_assignments.append(assignment)

    if len(vehicle_ids) == 1:
        mission.vehicle_id = vehicle_ids[0]

    if mission.status == MissionStatus.DRAFT:
        mission.status = MissionStatus.READY

    await db.flush()
    await _emit_assignment_updates(org_id, new_assignments)
    return [
        MissionAssignmentResponse(
            mission_id=a.mission_id,
            vehicle_id=a.vehicle_id,
            status=a.status,
            progress=a.progress,
            current_waypoint=a.current_waypoint,
            active=a.active,
            assigned_by=a.assigned_by,
            assigned_at=a.assigned_at,
            started_at=a.started_at,
            completed_at=a.completed_at,
        ) for a in new_assignments
    ]


async def unassign_mission(
    db: AsyncSession,
    org_id: UUID,
    mission_id: UUID,
    vehicle_ids: list[UUID],
    *,
    user: dict | None = None,
) -> int:
    await _get_mission(db, mission_id, org_id)
    for vehicle_id in vehicle_ids:
        await _assert_vehicle_access(db, org_id, vehicle_id, user)
    result = await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.mission_id == mission_id,
            MissionAssignment.vehicle_id.in_(vehicle_ids),
            MissionAssignment.active.is_(True),
        )
    )
    assignments = result.scalars().all()
    for assignment in assignments:
        assignment.active = False

    remaining = (await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.mission_id == mission_id,
            MissionAssignment.active.is_(True),
        )
    )).scalars().all()
    if not remaining:
        mission = await _get_mission(db, mission_id, org_id)
        mission.vehicle_id = None
    await db.flush()
    await _emit_assignment_updates(org_id, assignments)
    return len(assignments)


async def update_mission_status(
    db: AsyncSession,
    org_id: UUID,
    data: MissionStatusUpdateRequest,
) -> MissionAssignmentResponse:
    mission = await _get_mission(db, data.mission_id, org_id)
    assignment = (await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.mission_id == data.mission_id,
            MissionAssignment.vehicle_id == data.vehicle_id,
            MissionAssignment.active.is_(True),
        )
    )).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    assignment.status = data.status
    if data.progress is not None:
        assignment.progress = data.progress
    if data.current_waypoint is not None:
        assignment.current_waypoint = data.current_waypoint

    if data.status == MissionStatus.IN_PROGRESS and assignment.started_at is None:
        assignment.started_at = datetime.now(timezone.utc)
    if data.status in (MissionStatus.COMPLETED, MissionStatus.ABORTED, MissionStatus.FAILED):
        assignment.completed_at = datetime.now(timezone.utc)

    # Update mission aggregate status/progress
    active_assignments = (await db.execute(
        select(MissionAssignment).where(
            MissionAssignment.mission_id == data.mission_id,
            MissionAssignment.active.is_(True),
        )
    )).scalars().all()
    if active_assignments:
        mission.progress = sum(a.progress for a in active_assignments) / len(active_assignments)
        mission.status = data.status

    await db.flush()
    await _emit_assignment_updates(org_id, [assignment])
    return MissionAssignmentResponse(
        mission_id=assignment.mission_id,
        vehicle_id=assignment.vehicle_id,
        status=assignment.status,
        progress=assignment.progress,
        current_waypoint=assignment.current_waypoint,
        active=assignment.active,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        started_at=assignment.started_at,
        completed_at=assignment.completed_at,
    )


async def upload_mission_to_vehicle(
    db: AsyncSession,
    org_id: UUID,
    data: MissionUploadRequest,
    *,
    request_id: str | None = None,
) -> dict:
    """Publish mission to MQTT for edge agent to upload to Pixhawk."""
    mission = await _get_mission_response(db, data.mission_id, org_id)
    if not mission.waypoints:
        raise HTTPException(status_code=400, detail="Mission has no waypoints")

    # Publish via MQTT
    from backend.shared.mqtt_topics import MQTTTopics
    from backend.shared.mqtt_runtime import get_mqtt

    topic = MQTTTopics.mission_upload(str(org_id), str(data.vehicle_id))

    event = MissionUploadEvent(
        request_id=request_id or str(uuid4()),
        org_id=str(org_id),
        vehicle_id=str(data.vehicle_id),
        mission=mission,
        timestamp=datetime.now(timezone.utc),
    )
    payload = event.model_dump(mode="json")

    mqtt = await get_mqtt()
    started = time.perf_counter()
    await retry_async(lambda: mqtt.publish(topic, payload), retries=4, base_delay_s=0.25)
    MQTT_PUBLISH_LATENCY_SECONDS.labels("mission_upload").observe(time.perf_counter() - started)
    logger.info(f"Mission {data.mission_id} published for upload to vehicle {data.vehicle_id} on {topic}")

    # Update status
    result = await db.execute(select(Mission).where(Mission.id == data.mission_id))
    m = result.scalar_one()
    m.status = MissionStatus.UPLOADING
    m.vehicle_id = data.vehicle_id
    await db.flush()

    MISSION_UPLOAD_TOTAL.labels("accepted").inc()
    return {"status": "uploading", "mission_id": str(data.mission_id), "vehicle_id": str(data.vehicle_id)}


async def download_mission_from_vehicle(
    db: AsyncSession,
    org_id: UUID,
    data: MissionDownloadRequest,
    *,
    user: dict | None = None,
    timeout_s: float = 30.0,
    request_id: str | None = None,
) -> MissionResponse:
    """Request current mission from a vehicle via MQTT → edge agent → MAVLink."""
    await _assert_vehicle_access(db, org_id, data.vehicle_id, user)
    await _ensure_mission_download_listener()

    req_id = request_id or str(uuid4())
    now = datetime.now(timezone.utc)
    topic = MQTTTopics.mission_download_request(str(org_id), str(data.vehicle_id))
    mqtt = await get_mqtt()

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict] = loop.create_future()
    _mission_download_pending[req_id] = fut
    try:
        req_event = MissionDownloadRequestEvent(
            request_id=req_id,
            org_id=str(org_id),
            vehicle_id=str(data.vehicle_id),
            timestamp=now,
        )
        started = time.perf_counter()
        await retry_async(lambda: mqtt.publish(topic, req_event.model_dump(mode="json")), retries=4, base_delay_s=0.25)
        MQTT_PUBLISH_LATENCY_SECONDS.labels("mission_download").observe(time.perf_counter() - started)

        try:
            payload = await asyncio.wait_for(fut, timeout=timeout_s)
        except asyncio.TimeoutError:
            MISSION_DOWNLOAD_TOTAL.labels("timeout").inc()
            raise HTTPException(status_code=504, detail="Timed out waiting for mission download response")

        resp = MissionDownloadResponseEvent.model_validate(payload)
        if not resp.ok:
            raise HTTPException(status_code=502, detail=resp.message or "Mission download failed")
        if not resp.waypoints:
            raise HTTPException(status_code=502, detail="Vehicle returned empty mission")

        mission_name = data.name or f"Downloaded mission {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        created = await create_mission(
            db,
            org_id,
            MissionCreate(name=mission_name, vehicle_id=data.vehicle_id, waypoints=resp.waypoints),
            user=user,
        )
        MISSION_DOWNLOAD_TOTAL.labels("accepted").inc()
        return created
    finally:
        _mission_download_pending.pop(req_id, None)


async def get_mission_graph(
    db: AsyncSession, org_id: UUID, mission_id: UUID, *, user: dict | None = None
) -> MissionGraph:
    result = await db.execute(select(Mission).where(Mission.id == mission_id, Mission.organization_id == org_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    await _assert_mission_access(db, org_id, mission, user)

    settings = mission.settings or {}
    raw = settings.get(_MISSION_GRAPH_SETTINGS_KEY)
    if not raw:
        return MissionGraph()
    return MissionGraph.model_validate(raw)


async def update_mission_graph(
    db: AsyncSession,
    org_id: UUID,
    mission_id: UUID,
    graph: MissionGraph,
    *,
    user_id: str | None = None,
    user: dict | None = None,
) -> MissionGraph:
    result = await db.execute(select(Mission).where(Mission.id == mission_id, Mission.organization_id == org_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    await _assert_mission_access(db, org_id, mission, user)
    if mission.status not in (MissionStatus.DRAFT, MissionStatus.READY):
        raise HTTPException(status_code=400, detail="Cannot edit active mission")

    now = datetime.now(timezone.utc)
    graph.meta.updated_at = now
    if graph.meta.created_at is None:
        graph.meta.created_at = now
    if user_id:
        graph.meta.updated_by = user_id
        if graph.meta.created_by is None:
            graph.meta.created_by = user_id

    settings = dict(mission.settings or {})
    settings[_MISSION_GRAPH_SETTINGS_KEY] = graph.model_dump(mode="json")
    mission.settings = settings

    await db.flush()
    return graph


async def validate_mission_graph(
    db: AsyncSession, org_id: UUID, mission_id: UUID, *, user: dict | None = None
) -> ValidationResult:
    graph = await get_mission_graph(db, org_id, mission_id, user=user)
    issues: list[ValidationIssue] = []

    node_ids = [n.id for n in graph.nodes]
    if len(set(node_ids)) != len(node_ids):
        issues.append(
            ValidationIssue(
                severity=MissionSeverity.ERROR,
                code="DUPLICATE_NODE_ID",
                message="Graph contains duplicate node IDs",
            )
        )

    node_id_set = set(node_ids)
    edge_ids = [e.id for e in graph.edges]
    if len(set(edge_ids)) != len(edge_ids):
        issues.append(
            ValidationIssue(
                severity=MissionSeverity.ERROR,
                code="DUPLICATE_EDGE_ID",
                message="Graph contains duplicate edge IDs",
            )
        )

    for e in graph.edges:
        if e.from_node not in node_id_set:
            issues.append(
                ValidationIssue(
                    severity=MissionSeverity.ERROR,
                    code="EDGE_FROM_MISSING",
                    message=f"Edge '{e.id}' references missing from_node '{e.from_node}'",
                    node_id=e.from_node,
                )
            )
        if e.to_node not in node_id_set:
            issues.append(
                ValidationIssue(
                    severity=MissionSeverity.ERROR,
                    code="EDGE_TO_MISSING",
                    message=f"Edge '{e.id}' references missing to_node '{e.to_node}'",
                    node_id=e.to_node,
                )
            )
        if e.type == MissionEdgeType.CONDITIONAL and not e.condition:
            issues.append(
                ValidationIssue(
                    severity=MissionSeverity.WARNING,
                    code="CONDITION_EMPTY",
                    message=f"Conditional edge '{e.id}' has no condition expression",
                )
            )

    if not any(n.type == MissionNodeType.START for n in graph.nodes):
        issues.append(
            ValidationIssue(
                severity=MissionSeverity.WARNING,
                code="NO_START_NODE",
                message="No START node found (recommended for guided missions)",
            )
        )

    waypoint_nodes = [n for n in graph.nodes if n.type in (MissionNodeType.WAYPOINT, MissionNodeType.PATH_POINT)]
    if not waypoint_nodes:
        issues.append(
            ValidationIssue(
                severity=MissionSeverity.ERROR,
                code="NO_WAYPOINTS",
                message="Graph has no waypoint/path nodes",
            )
        )
    else:
        for n in waypoint_nodes:
            if n.position is None:
                issues.append(
                    ValidationIssue(
                        severity=MissionSeverity.ERROR,
                        code="WAYPOINT_NO_POSITION",
                        message="Waypoint node has no position",
                        node_id=n.id,
                    )
                )

    ok = not any(i.severity == MissionSeverity.ERROR for i in issues)
    return ValidationResult(ok=ok, issues=issues)


async def compile_mission_graph(
    db: AsyncSession, org_id: UUID, mission_id: UUID, *, user: dict | None = None
) -> CompileResult:
    validation = await validate_mission_graph(db, org_id, mission_id, user=user)
    if not validation.ok:
        raise HTTPException(status_code=400, detail={"message": "Graph validation failed", "issues": validation.model_dump(mode="json")})

    graph = await get_mission_graph(db, org_id, mission_id, user=user)
    waypoint_nodes = [n for n in graph.nodes if n.type in (MissionNodeType.WAYPOINT, MissionNodeType.PATH_POINT)]
    waypoint_nodes.sort(key=lambda n: (n.seq, n.id))

    waypoints: list[CompiledWaypoint] = []
    for i, node in enumerate(waypoint_nodes):
        if node.position is None:
            continue
        waypoints.append(
            CompiledWaypoint(
                seq=i,
                lat=node.position.lat,
                lng=node.position.lng,
                alt=node.position.alt,
                command="NAV_WAYPOINT",
                frame=3,
            )
        )

    return CompileResult(mission_id=mission_id, graph_version=graph.meta.graph_version, waypoints=waypoints)


# ── Helpers ──

async def _get_mission_response(db: AsyncSession, mission_id: UUID, org_id: UUID) -> MissionResponse:
    result = await db.execute(
        select(Mission).where(Mission.id == mission_id, Mission.organization_id == org_id)
        .options(selectinload(Mission.waypoints), selectinload(Mission.assignments))
    )
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _mission_to_response(mission)


def _mission_to_response(m: Mission) -> MissionResponse:
    assignments = [
        MissionAssignmentResponse(
            mission_id=a.mission_id,
            vehicle_id=a.vehicle_id,
            status=a.status,
            progress=a.progress,
            current_waypoint=a.current_waypoint,
            active=a.active,
            assigned_by=a.assigned_by,
            assigned_at=a.assigned_at,
            started_at=a.started_at,
            completed_at=a.completed_at,
        ) for a in (m.assignments or [])
    ]
    return MissionResponse(
        id=m.id, name=m.name, description=m.description, status=m.status,
        vehicle_id=m.vehicle_id, type=m.type, settings=m.settings,
        progress=m.progress, current_waypoint=m.current_waypoint,
        total_distance=m.total_distance, estimated_duration=m.estimated_duration,
        started_at=m.started_at, completed_at=m.completed_at,
        created_at=m.created_at, organization_id=m.organization_id,
        assigned_vehicle_ids=[a.vehicle_id for a in assignments if a.active],
        assignments=assignments,
        waypoints=[
            WaypointResponse(
                id=wp.id, seq=wp.seq, lat=wp.lat, lng=wp.lng, alt=wp.alt,
                command=wp.command, frame=wp.frame,
                param1=wp.param1, param2=wp.param2, param3=wp.param3, param4=wp.param4,
            ) for wp in m.waypoints
        ],
    )


async def _get_mission(db: AsyncSession, mission_id: UUID, org_id: UUID) -> Mission:
    result = await db.execute(
        select(Mission).where(Mission.id == mission_id, Mission.organization_id == org_id)
        .options(selectinload(Mission.waypoints), selectinload(Mission.assignments))
    )
    mission = result.scalar_one_or_none()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


async def _get_allowed_vehicle_ids(db: AsyncSession, org_id: UUID, user: dict | None) -> set[UUID] | None:
    if not user:
        return None
    role = user.get("role")
    if role in (Role.ADMIN.value, Role.SUPER_ADMIN.value):
        return None
    user_id = user.get("user_id")
    if not user_id:
        return set()

    fleet_ids = (await db.execute(
        select(FleetUserAssignment.fleet_id)
        .join(Vehicle, Vehicle.fleet_id == FleetUserAssignment.fleet_id)
        .where(FleetUserAssignment.user_id == UUID(user_id), Vehicle.organization_id == org_id)
    )).scalars().all()
    if not fleet_ids:
        return set()

    vehicle_ids = (await db.execute(
        select(Vehicle.id).where(Vehicle.organization_id == org_id, Vehicle.fleet_id.in_(fleet_ids))
    )).scalars().all()
    return set(vehicle_ids)


async def _assert_mission_access(db: AsyncSession, org_id: UUID, mission: Mission, user: dict | None) -> None:
    allowed = await _get_allowed_vehicle_ids(db, org_id, user)
    if allowed is None:
        return
    if not allowed:
        raise HTTPException(status_code=403, detail="Fleet access denied")

    if not mission.assignments:
        raise HTTPException(status_code=403, detail="Fleet access denied")

    if not any(a.vehicle_id in allowed for a in mission.assignments if a.active):
        raise HTTPException(status_code=403, detail="Fleet access denied")


async def _assert_vehicle_access(db: AsyncSession, org_id: UUID, vehicle_id: UUID, user: dict | None) -> None:
    allowed = await _get_allowed_vehicle_ids(db, org_id, user)
    if allowed is None:
        return
    if vehicle_id not in allowed:
        raise HTTPException(status_code=403, detail="Fleet access denied")


async def _emit_assignment_updates(org_id: UUID, assignments: list[MissionAssignment]) -> None:
    if not assignments:
        return
    mqtt = await get_mqtt()
    for assignment in assignments:
        payload = {
            "mission_id": str(assignment.mission_id),
            "vehicle_id": str(assignment.vehicle_id),
            "status": assignment.status.value if hasattr(assignment.status, "value") else assignment.status,
            "progress": assignment.progress,
            "current_waypoint": assignment.current_waypoint,
            "active": assignment.active,
            "assigned_at": assignment.assigned_at.isoformat(),
        }
        topic = MQTTTopics.mission_status(str(org_id), str(assignment.vehicle_id))
        await retry_async(lambda: mqtt.publish(topic, payload), retries=4, base_delay_s=0.25)
        await ws_manager.broadcast_mission(str(assignment.vehicle_id), str(org_id), payload)


def _calculate_distance(waypoints) -> float:
    """Calculate total mission distance in meters using Haversine."""
    total = 0.0
    for i in range(1, len(waypoints)):
        a, b = waypoints[i - 1], waypoints[i]
        total += _haversine(a.lat, a.lng, b.lat, b.lng)
    return round(total, 1)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

