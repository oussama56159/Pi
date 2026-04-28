"""
Service Proxy Router
=====================
Routes API requests to the appropriate microservice.
In monolith-mode: directly imports service routers.
In microservice-mode: proxies via HTTP to individual service URLs.

This module supports both modes for development flexibility.
"""
from __future__ import annotations

from fastapi import APIRouter

from .actions import router as actions_router

# ── Import service routers directly (monolith mode) ──
# In production microservice deployment, replace these with HTTP proxy
from backend.services.auth.routes import router as auth_router
from backend.services.fleet.routes import router as fleet_router
from backend.services.telemetry.routes import router as telemetry_router
from backend.services.mission.routes import router as mission_router
from backend.services.command.routes import router as command_router
from backend.services.alert.routes import router as alert_router
from backend.services.vision.routes import router as vision_router

router = APIRouter(prefix="/api/v1")

# Mount all service routers under /api/v1
router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(fleet_router, prefix="/fleet", tags=["Fleet & Vehicles"])
router.include_router(telemetry_router, prefix="/telemetry", tags=["Telemetry"])
router.include_router(mission_router, prefix="/missions", tags=["Missions"])
router.include_router(command_router, prefix="/commands", tags=["Commands"])
router.include_router(alert_router, prefix="/alerts", tags=["Alerts"])
router.include_router(vision_router, prefix="/vision", tags=["Vision"])

# Gateway-level routes
router.include_router(actions_router, tags=["Actions"])

