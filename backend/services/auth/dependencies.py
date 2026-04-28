"""
FastAPI dependencies for authentication & authorization.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from backend.shared.schemas.auth import Role, ROLE_HIERARCHY


def get_current_user(request: Request) -> dict:
    """Extract user context injected by JWT middleware."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {
        "user_id": user_id,
        "role": getattr(request.state, "user_role", None),
        "org_id": getattr(request.state, "org_id", None),
        "request_id": getattr(request.state, "request_id", None),
    }


CurrentUser = Annotated[dict, Depends(get_current_user)]


class RequireRole:
    """
    Dependency that enforces minimum role level.

    Usage:
        @router.get("/admin", dependencies=[Depends(RequireRole(Role.ADMIN))])
    """

    def __init__(self, minimum_role: Role):
        self.minimum_level = ROLE_HIERARCHY[minimum_role]

    def __call__(self, user: CurrentUser):
        user_role = user.get("role")
        if not user_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No role assigned")

        try:
            role_enum = Role(user_role)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")

        if ROLE_HIERARCHY.get(role_enum, 0) < self.minimum_level:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

        return user


def get_org_id(user: CurrentUser) -> UUID:
    """Extract and validate organization ID from user context."""
    org_id = user.get("org_id")
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")
    return UUID(org_id)


OrgId = Annotated[UUID, Depends(get_org_id)]

