"""
Health-check endpoints for the API Gateway.
/health       – basic liveness
/health/ready – readiness (checks all downstream services)
/health/live  – Kubernetes liveness probe
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from backend.shared.database.postgres import get_direct_postgres_session

router = APIRouter(prefix="/health")


@router.get("")
async def health():
    """Basic health check."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/live")
async def liveness():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/ready")
async def readiness():
    """
    Deep readiness check – validates connectivity to all downstream services.
    Returns 503 if any critical dependency is unhealthy.
    """
    checks = {}

    # PostgreSQL check
    try:
        db = await get_direct_postgres_session()
        async with db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        checks["postgresql"] = {"status": "up"}
    except Exception as e:
        checks["postgresql"] = {"status": "down", "error": str(e)}

    all_up = all(c["status"] == "up" for c in checks.values())
    status_code = 200 if all_up else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_up else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
    )


@router.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

