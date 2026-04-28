"""
AeroCommand API Gateway
========================
Central entry point for all REST & WebSocket traffic.
- JWT validation middleware
- Rate limiting
- Request routing to microservices
- Health-check aggregation
- CORS handling
- OpenAPI documentation aggregation
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
import asyncio
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.shared.config import get_base_settings
from backend.shared.database import init_postgres
from backend.shared.database.postgres import ensure_schema
from backend.shared.database.postgres import get_postgres_session

from backend.services.mission.mqtt_listener import start_mission_status_listener
from backend.services.telemetry.mqtt_listener import start_telemetry_listener
from backend.services.command.mqtt_listener import start_command_ack_listener
from backend.services.alert.mqtt_listener import start_alert_listener
from backend.services.auth.seed import ensure_auth_runtime_schema, ensure_owner_account
from backend.shared.mqtt_runtime import close_mqtt

from .middleware.rate_limiter import RateLimiterMiddleware
from .middleware.auth import JWTAuthMiddleware
from .routes import health, proxy


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    settings = get_base_settings()
    await init_postgres()
    if settings.AUTO_CREATE_DB or settings.DEBUG:
        await ensure_schema()
        async for db in get_postgres_session():
            await ensure_auth_runtime_schema(db)
            await ensure_owner_account(db)
            await db.commit()
            break

    # MQTT topic subscriptions (these return quickly after registering handlers)
    mission_task = asyncio.create_task(start_mission_status_listener())
    telemetry_task = asyncio.create_task(start_telemetry_listener())
    command_task = asyncio.create_task(start_command_ack_listener())
    alert_task = asyncio.create_task(start_alert_listener())

    yield
    for task in (mission_task, telemetry_task, command_task, alert_task):
        task.cancel()
    await close_mqtt()


def create_app() -> FastAPI:
    settings = get_base_settings()

    app = FastAPI(
        title="AeroCommand API Gateway",
        version=settings.SERVICE_VERSION,
        description="Unified gateway for the AeroCommand Drone & Robot Fleet Management Platform",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware (outermost → innermost) ──
    app.add_middleware(RateLimiterMiddleware)
    app.add_middleware(JWTAuthMiddleware)

    # ── Request timing ──
    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.2f}ms"
        response.headers["X-Request-Id"] = request_id
        return response

    # ── Global exception handler ──
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    # ── Routes ──
    app.include_router(health.router, tags=["Health"])
    app.include_router(proxy.router)

    return app


app = create_app()

