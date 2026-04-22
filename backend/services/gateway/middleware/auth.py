"""
JWT Authentication Middleware
==============================
Validates Bearer tokens on protected routes.
Injects user context into request.state for downstream handlers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.shared.config import get_base_settings
from backend.shared.database.postgres import get_direct_postgres_session
from backend.shared.runtime_cache import get_runtime_cache
from backend.services.auth.models import Organization, User
from backend.shared.schemas.auth import Role

# Routes that do NOT require authentication
PUBLIC_PATHS = frozenset({
    "/",
    "/health",
    "/health/ready",
    "/health/live",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/password-recovery-request",
    "/api/v1/auth/refresh",
})

PUBLIC_PREFIXES = ("/api/v1/auth/oauth",)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validates JWT and injects user context into request.state."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow CORS preflight to pass through to CORSMiddleware
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip auth for public routes
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return await call_next(request)

        # Skip WebSocket upgrade (handled separately)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing authentication token"})

        token = auth_header[7:]
        settings = get_base_settings()

        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except ExpiredSignatureError:
            return JSONResponse(status_code=401, content={"detail": "Token expired"})
        except JWTError:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        # Check token blacklist (logout / revocation)
        jti = payload.get("jti")
        if jti:
            if get_runtime_cache().is_token_blacklisted(jti):
                return JSONResponse(status_code=401, content={"detail": "Token revoked"})

        # Inject user context
        user_id = payload.get("sub")
        try:
            db = await get_direct_postgres_session()
            async with db as session:
                result = await session.execute(
                    select(User).where(User.id == UUID(user_id))
                )
                db_user = result.scalar_one_or_none()
                if not db_user:
                    return JSONResponse(status_code=401, content={"detail": "User not found"})
                if not db_user.is_active:
                    return JSONResponse(status_code=401, content={"detail": "User disabled"})
                if db_user.expires_at and db_user.expires_at <= datetime.now(timezone.utc):
                    return JSONResponse(status_code=401, content={"detail": "User account expired"})

                if db_user.role != Role.SUPER_ADMIN and db_user.organization_id:
                    org = (
                        await session.execute(
                            select(Organization).where(Organization.id == db_user.organization_id)
                        )
                    ).scalar_one_or_none()
                    if org and (not org.is_active or (org.expires_at and org.expires_at <= datetime.now(timezone.utc))):
                        return JSONResponse(status_code=401, content={"detail": "Organization is inactive or expired"})
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "Unable to validate session"})

        request.state.user_id = str(db_user.id)
        request.state.user_role = db_user.role.value
        request.state.org_id = str(db_user.organization_id) if db_user.organization_id else None
        request.state.token_jti = jti

        return await call_next(request)

