"""Action semantics endpoints.

- Registry: serve baseline action metadata.
- Audit: ingest action audit events into an in-memory runtime log.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from backend.services.auth.dependencies import CurrentUser, RequireRole
from backend.shared.action_registry import get_action_registry
from backend.shared.runtime_cache import get_runtime_cache
from backend.shared.schemas.action_semantics import ActionAuditEvent, ActionRegistryResponse
from backend.shared.schemas.auth import Role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions")


@router.get("/registry", response_model=ActionRegistryResponse, dependencies=[Depends(RequireRole(Role.VIEWER))])
async def registry() -> ActionRegistryResponse:
    """Return the server-side action registry."""

    return get_action_registry()


@router.post("/audit", status_code=202, dependencies=[Depends(RequireRole(Role.VIEWER))])
async def ingest_audit_event(request: Request, event: ActionAuditEvent, user: CurrentUser) -> dict[str, Any]:
    """Ingest an action audit event.

    Persists to an in-memory runtime log.
    """

    # Fill actor/org if client didn't include it.
    if not event.user_id:
        event.user_id = str(user.get("user_id"))
    if not event.org_id:
        event.org_id = str(user.get("org_id")) if user.get("org_id") else None

    # Prefer gateway request id header if present.
    if not event.request_id:
        event.request_id = request.headers.get("X-Request-Id") or None

    record = {
        **event.model_dump(mode="json"),
        "actor_role": user.get("role"),
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("User-Agent"),
    }

    stream_id = get_runtime_cache().append_audit_event(record)

    logger.info("action_audit_ingest action_id=%s outcome=%s stream_id=%s", event.action_id, event.outcome, stream_id)

    return {"accepted": True, "storage": "memory", "id": stream_id}
