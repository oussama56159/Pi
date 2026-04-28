"""Mission REST API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.database.postgres import get_postgres_session
from backend.shared.schemas.auth import Role
from backend.shared.schemas.mission import (
    MissionAssignRequest,
    MissionAssignmentResponse,
    MissionCreate,
    MissionDownloadRequest,
    MissionResponse,
    MissionStatus,
    MissionStatusUpdateRequest,
    MissionUnassignRequest,
    MissionUpdate,
    MissionUploadRequest,
)
from backend.shared.schemas.mission_graph import CompileResult, MissionGraph, ValidationResult

from backend.services.auth.dependencies import CurrentUser, OrgId, RequireRole
from .service import (
    assign_mission,
    compile_mission_graph,
    create_mission,
    delete_mission,
    download_mission_from_vehicle,
    get_mission,
    get_mission_graph,
    list_missions,
    unassign_mission,
    update_mission,
    update_mission_graph,
    upload_mission_to_vehicle,
    update_mission_status,
    validate_mission_graph,
)

router = APIRouter()


@router.get("", response_model=list[MissionResponse])
async def api_list_missions(
    org_id: OrgId,
    user: CurrentUser,
    vehicle_id: UUID | None = None,
    status: MissionStatus | None = None,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await list_missions(db, org_id, vehicle_id, status, user=user)


@router.post("", response_model=MissionResponse, status_code=201,
             dependencies=[Depends(RequireRole(Role.OPERATOR))])
async def api_create_mission(
    data: MissionCreate,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await create_mission(db, org_id, data, user=user)


@router.get("/{mission_id}", response_model=MissionResponse)
async def api_get_mission(
    mission_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await get_mission(db, org_id, mission_id, user=user)


@router.patch("/{mission_id}", response_model=MissionResponse,
              dependencies=[Depends(RequireRole(Role.OPERATOR))])
async def api_update_mission(
    mission_id: UUID,
    data: MissionUpdate,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await update_mission(db, org_id, mission_id, data, user=user)


@router.delete("/{mission_id}", status_code=204,
               dependencies=[Depends(RequireRole(Role.OPERATOR))])
async def api_delete_mission(
    mission_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    await delete_mission(db, org_id, mission_id, user=user)


@router.post(
    "/{mission_id}/assign",
    response_model=list[MissionAssignmentResponse],
    dependencies=[Depends(RequireRole(Role.OPERATOR))],
)
async def api_assign_mission(
    mission_id: UUID,
    data: MissionAssignRequest,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await assign_mission(
        db,
        org_id,
        mission_id,
        data.vehicle_ids,
        assigned_by=user.get("user_id"),
        replace_existing=data.replace_existing,
        user=user,
    )


@router.post(
    "/{mission_id}/unassign",
    dependencies=[Depends(RequireRole(Role.OPERATOR))],
)
async def api_unassign_mission(
    mission_id: UUID,
    data: MissionUnassignRequest,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    count = await unassign_mission(db, org_id, mission_id, data.vehicle_ids, user=user)
    return {"status": "ok", "unassigned": count}


@router.post(
    "/status",
    response_model=MissionAssignmentResponse,
    dependencies=[Depends(RequireRole(Role.PILOT))],
)
async def api_update_mission_status(
    data: MissionStatusUpdateRequest,
    org_id: OrgId,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await update_mission_status(db, org_id, data)


@router.post("/upload", dependencies=[Depends(RequireRole(Role.PILOT))])
async def api_upload_mission(
    request: Request,
    data: MissionUploadRequest,
    org_id: OrgId,
    db: AsyncSession = Depends(get_postgres_session),
):
    """Upload a mission to a vehicle via MQTT → edge agent → Pixhawk."""
    return await upload_mission_to_vehicle(db, org_id, data, request_id=getattr(request.state, "request_id", None))


@router.post(
    "/download",
    response_model=MissionResponse,
    dependencies=[Depends(RequireRole(Role.PILOT))],
)
async def api_download_mission(
    request: Request,
    data: MissionDownloadRequest,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    """Download current mission from a vehicle via MQTT → edge agent → Pixhawk."""
    return await download_mission_from_vehicle(
        db,
        org_id,
        data,
        user=user,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get("/{mission_id}/graph", response_model=MissionGraph)
async def api_get_mission_graph(
    mission_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await get_mission_graph(db, org_id, mission_id, user=user)


@router.put(
    "/{mission_id}/graph",
    response_model=MissionGraph,
    dependencies=[Depends(RequireRole(Role.OPERATOR))],
)
async def api_update_mission_graph(
    mission_id: UUID,
    data: MissionGraph,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await update_mission_graph(db, org_id, mission_id, data, user_id=user.get("user_id"), user=user)


@router.post("/{mission_id}/graph/validate", response_model=ValidationResult)
async def api_validate_mission_graph(
    mission_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await validate_mission_graph(db, org_id, mission_id, user=user)


@router.post("/{mission_id}/graph/compile", response_model=CompileResult)
async def api_compile_mission_graph(
    mission_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await compile_mission_graph(db, org_id, mission_id, user=user)

