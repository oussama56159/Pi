"""Command & Control REST API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.database.postgres import get_postgres_session
from backend.shared.schemas.auth import Role
from backend.shared.schemas.command import CommandRequest, CommandResponse

from backend.services.auth.dependencies import CurrentUser, OrgId, RequireRole
from .service import dispatch_command, get_command, list_commands

router = APIRouter()


@router.post("", response_model=CommandResponse, status_code=201,
             dependencies=[Depends(RequireRole(Role.PILOT))])
async def api_dispatch_command(
    data: CommandRequest,
    user: CurrentUser,
    org_id: OrgId,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_postgres_session),
):
    """Send a command to a vehicle (pilot+ role required)."""
    resolved_idempotency_key = idempotency_key or data.idempotency_key
    if not resolved_idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header (or idempotency_key body field) is required")
    request_data = data.model_copy(update={"idempotency_key": resolved_idempotency_key})
    return await dispatch_command(db, org_id, UUID(user["user_id"]), request_data, user=user)


@router.get("", response_model=list[CommandResponse])
async def api_list_commands(
    org_id: OrgId,
    vehicle_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_postgres_session),
):
    return await list_commands(db, org_id, vehicle_id, limit)


@router.get("/{command_id}", response_model=CommandResponse)
async def api_get_command(
    command_id: UUID,
    org_id: OrgId,
    db: AsyncSession = Depends(get_postgres_session),
):
    return await get_command(db, org_id, command_id)

