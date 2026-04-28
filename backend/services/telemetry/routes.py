"""Telemetry REST + WebSocket routes."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from sqlalchemy import select

from backend.services.auth.dependencies import CurrentUser, OrgId
from backend.shared.config import get_base_settings
from backend.shared.database.postgres import get_postgres_session, get_direct_postgres_session
from backend.shared.runtime_cache import get_runtime_cache
from backend.services.auth.models import Organization, User
from backend.shared.schemas.auth import Role
from backend.services.fleet.service import ensure_vehicle_access
from sqlalchemy.ext.asyncio import AsyncSession
from backend.shared.schemas.telemetry import TelemetryHistoryResponse

from .service import get_latest_snapshot, get_telemetry_history
from .websocket_manager import ws_manager

router = APIRouter()


async def _resolve_ws_user(ws: WebSocket) -> tuple[dict, UUID]:
    token = ws.query_params.get("access_token") or ws.query_params.get("token")
    if not token:
        raise ValueError("Missing authentication token")

    settings = get_base_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        raise ValueError("Token expired") from exc
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    jti = payload.get("jti")
    if jti and await get_runtime_cache().is_token_blacklisted(jti):
        raise ValueError("Token revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid token payload")

    db = await get_direct_postgres_session()
    async with db as session:
        result = await session.execute(select(User).where(User.id == UUID(user_id)))
        db_user = result.scalar_one_or_none()
        if not db_user or not db_user.is_active:
            raise ValueError("User not found or disabled")

        if db_user.expires_at and db_user.expires_at <= datetime.now(timezone.utc):
            raise ValueError("User account expired")

        if db_user.role != Role.SUPER_ADMIN and db_user.organization_id:
            org = (
                await session.execute(select(Organization).where(Organization.id == db_user.organization_id))
            ).scalar_one_or_none()
            if org and (not org.is_active or (org.expires_at and org.expires_at <= datetime.now(timezone.utc))):
                raise ValueError("Organization inactive or expired")

    org_id = db_user.organization_id
    if org_id is None:
        raise ValueError("Organization context required")
    user_ctx = {"user_id": str(db_user.id), "role": db_user.role.value, "org_id": str(org_id)}
    return user_ctx, org_id


async def _validate_channels(channels: list[str], user_ctx: dict, org_id: UUID) -> None:
    db = await get_direct_postgres_session()
    async with db as session:
        for channel in channels:
            if channel.startswith("vehicle:"):
                _, vehicle_id = channel.split(":", 1)
                await ensure_vehicle_access(session, org_id, UUID(vehicle_id), user_ctx)
                continue
            if channel.startswith("org:") or channel.startswith("alerts:"):
                _, chan_org = channel.split(":", 1)
                if chan_org != str(org_id):
                    raise ValueError("Channel organization mismatch")
                continue
            raise ValueError("Unsupported channel type")


@router.get("/vehicles/{vehicle_id}/latest")
async def api_latest_telemetry(
    vehicle_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
):
    """Get the latest cached telemetry snapshot for a vehicle."""
    await ensure_vehicle_access(db, org_id, vehicle_id, user)
    data = await get_latest_snapshot(str(vehicle_id))
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No telemetry data available")
    return data


@router.get("/vehicles/{vehicle_id}/history", response_model=TelemetryHistoryResponse)
async def api_telemetry_history(
    vehicle_id: UUID,
    org_id: OrgId,
    user: CurrentUser,
    db: AsyncSession = Depends(get_postgres_session),
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    resolution: str = Query("1s"),
):
    """Query historical telemetry data from PostgreSQL."""
    await ensure_vehicle_access(db, org_id, vehicle_id, user)
    points = await get_telemetry_history(str(vehicle_id), start_time, end_time, resolution)
    return TelemetryHistoryResponse(
        vehicle_id=str(vehicle_id),
        start_time=start_time,
        end_time=end_time,
        resolution=resolution,
        points=points,
        total_points=len(points),
    )


@router.websocket("/ws")
async def telemetry_websocket(ws: WebSocket):
    """
    WebSocket endpoint for real-time telemetry streaming.

    Connect with query params:
        ?channels=vehicle:abc123,org:myorg,alerts:myorg

    Messages sent to client:
        {"type": "telemetry", "vehicle_id": "...", "data": {...}}
        {"type": "alert", "data": {...}}
    """
    channels_param = ws.query_params.get("channels", "")
    channels = [c.strip() for c in channels_param.split(",") if c.strip()]

    if not channels:
        await ws.close(code=4000, reason="No channels specified")
        return

    try:
        user_ctx, org_id = await _resolve_ws_user(ws)
        await _validate_channels(channels, user_ctx, org_id)
    except Exception as exc:
        await ws.close(code=4403, reason=str(exc))
        return

    await ws_manager.connect(ws, channels)

    try:
        while True:
            # Keep connection alive; handle client messages if needed
            data = await ws.receive_text()
            # Client can send subscription changes
            try:
                import json
                msg = json.loads(data)
                if msg.get("action") == "subscribe":
                    new_channels = msg.get("channels", [])
                    await _validate_channels(new_channels, user_ctx, org_id)
                    await ws_manager.subscribe(ws, new_channels)
                elif msg.get("action") == "unsubscribe":
                    await ws_manager.unsubscribe(ws, msg.get("channels", []))
            except Exception:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)

