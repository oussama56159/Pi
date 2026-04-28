from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl

from backend.services.auth.dependencies import CurrentUser, OrgId, RequireRole
from backend.shared.config import get_base_settings
from backend.shared.schemas.auth import Role

from .service import get_vision_import_error, get_vision_service

router = APIRouter()


class StreamStartRequest(BaseModel):
    source_url: HttpUrl


class StreamStateResponse(BaseModel):
    vehicle_id: str
    source_url: str
    running: bool
    started_at: str | None
    updated_at: str | None
    fps: float
    inference_ms: float
    error: str | None
    counts: dict[str, int]
    detections: list[dict[str, Any]]


@router.post(
    "/streams/{vehicle_id}/start",
    response_model=StreamStateResponse,
    dependencies=[Depends(RequireRole(Role.OPERATOR))],
)
async def start_stream(
    vehicle_id: UUID,
    data: StreamStartRequest,
    org_id: OrgId,
    user: CurrentUser,
):
    if not get_base_settings().VISION_ENABLED:
        raise HTTPException(status_code=400, detail="Vision analytics is disabled")
    err = get_vision_import_error()
    if err:
        raise HTTPException(status_code=503, detail=f"Vision dependencies unavailable: {err}")
    state = get_vision_service().start_stream(str(vehicle_id), str(data.source_url))
    return StreamStateResponse(**state.__dict__)


@router.post(
    "/streams/{vehicle_id}/stop",
    dependencies=[Depends(RequireRole(Role.OPERATOR))],
)
async def stop_stream(
    vehicle_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
):
    stopped = get_vision_service().stop_stream(str(vehicle_id))
    return {"stopped": stopped}


@router.get("/streams/{vehicle_id}/detections/latest", response_model=StreamStateResponse)
async def latest_detections(
    vehicle_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
):
    state = get_vision_service().get_state(str(vehicle_id))
    if state is None:
        raise HTTPException(status_code=404, detail="Vision stream is not running for this vehicle")
    return StreamStateResponse(**state.__dict__)


@router.get("/streams/{vehicle_id}/annotated.mjpg")
async def annotated_stream(
    vehicle_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
):
    buffer = get_vision_service().get_stream_buffer(str(vehicle_id))
    if buffer is None:
        raise HTTPException(status_code=404, detail="Vision stream is not running for this vehicle")
    return StreamingResponse(
        buffer.stream(boundary="frame"),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

