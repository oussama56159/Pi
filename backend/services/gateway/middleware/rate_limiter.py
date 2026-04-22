"""
In-memory rate limiter.
Provides per-IP and per-user rate limiting for a single process.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.shared.runtime_cache import get_runtime_cache

# Default limits
RATE_LIMIT_PER_MINUTE = 120


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter using in-memory buckets."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Determine rate-limit key: authenticated user or IP
        client_id = getattr(request.state, "user_id", None)
        if not client_id:
            client_id = request.client.host if request.client else "unknown"

        if not get_runtime_cache().allow_rate_limit(client_id, RATE_LIMIT_PER_MINUTE, 60):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        return response

