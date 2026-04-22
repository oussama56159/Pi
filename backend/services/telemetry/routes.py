"""Telemetry REST + WebSocket routes."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from backend.services.auth.dependencies import CurrentUser, OrgId
from backend.shared.database.postgres import get_postgres_session
from backend.services.fleet.service import ensure_vehicle_access
from sqlalchemy.ext.asyncio import AsyncSession
from backend.shared.schemas.telemetry import TelemetryHistoryResponse

from .service import get_latest_snapshot, get_telemetry_history
from .websocket_manager import ws_manager

router = APIRouter()


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
                    for ch in new_channels:
                        ws_manager._subscriptions[ch].add(ws)
                        ws_manager._ws_channels[ws].add(ch)
                elif msg.get("action") == "unsubscribe":
                    for ch in msg.get("channels", []):
                        ws_manager._subscriptions[ch].discard(ws)
                        ws_manager._ws_channels[ws].discard(ch)
            except Exception:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)

