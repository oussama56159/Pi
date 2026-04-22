"""
Auth business logic – user registration, login, token management.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.shared.schemas.auth import (
    LoginRequest,
    LoginResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    Role,
    TokenRefreshResponse,
    UserCreate,
    UserUpdate,
    UserResponse,
)
from backend.shared.runtime_cache import get_runtime_cache

from .models import Organization, User
from .security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_expired(expires_at: datetime | None) -> bool:
    return bool(expires_at and expires_at <= _now())


async def _get_actor_user(db: AsyncSession, actor: dict) -> User:
    actor_id = actor.get("user_id")
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db_user = (await db.execute(select(User).where(User.id == UUID(actor_id)))).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=401, detail="Actor not found")
    return db_user


async def _ensure_organization_exists(db: AsyncSession, organization_id: UUID | None) -> None:
    if organization_id is None:
        return
    org = (await db.execute(select(Organization).where(Organization.id == organization_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")


def _resolve_role(role_value: str | Role | None) -> Role:
    try:
        return Role(role_value)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid role") from exc


def _can_manage_user(actor_role: Role, target_role: Role) -> bool:
    if actor_role == Role.SUPER_ADMIN:
        return True
    if actor_role == Role.ADMIN:
        return target_role not in {Role.ADMIN, Role.SUPER_ADMIN}
    return False


async def register_user(db: AsyncSession, data: UserCreate) -> UserResponse:
    """Register a new user."""
    # Check duplicate email
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        name=data.name,
        role=data.role,
        organization_id=data.organization_id,
        expires_at=data.expires_at,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)


async def create_user_by_admin(db: AsyncSession, actor: dict, data: UserCreate) -> UserResponse:
    """Create user from admin/super-admin context with org/role guardrails."""
    actor_role = _resolve_role(actor.get("role"))
    actor_org_id = actor.get("org_id")

    if actor_role == Role.ADMIN and data.role in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Admins cannot create admin-level users")

    org_id = data.organization_id
    if actor_role == Role.ADMIN:
        if not actor_org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        org_id = UUID(actor_org_id)
    elif actor_role == Role.SUPER_ADMIN and org_id is None and actor_org_id:
        org_id = UUID(actor_org_id)

    if data.role == Role.ADMIN and org_id is None:
        raise HTTPException(status_code=400, detail="Admin must be assigned to one organization")

    await _ensure_organization_exists(db, org_id)

    return await register_user(
        db,
        UserCreate(
            email=data.email,
            password=data.password,
            name=data.name,
            role=data.role,
            organization_id=org_id,
            expires_at=data.expires_at,
        ),
    )


async def create_organization_by_owner(db: AsyncSession, actor: dict, data: OrganizationCreate) -> OrganizationResponse:
    """Create organization by owner and assign it to owner if no org is set."""
    existing = (await db.execute(select(Organization).where(Organization.slug == data.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Organization slug already exists")

    org = Organization(name=data.name, slug=data.slug, is_active=True, expires_at=data.expires_at)
    db.add(org)
    await db.flush()

    actor_id = actor.get("user_id")
    if actor_id and not actor.get("org_id"):
        user = (await db.execute(select(User).where(User.id == UUID(actor_id)))).scalar_one_or_none()
        if user:
            user.organization_id = org.id

    await db.flush()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org)


async def list_users_for_actor(db: AsyncSession, actor: dict) -> list[UserResponse]:
    actor_role = _resolve_role(actor.get("role"))
    stmt = select(User)

    if actor_role == Role.ADMIN:
        actor_org_id = actor.get("org_id")
        if not actor_org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        stmt = stmt.where(User.organization_id == UUID(actor_org_id))

    users = (await db.execute(stmt)).scalars().all()
    return [UserResponse.model_validate(u) for u in users]


async def get_user_for_actor(db: AsyncSession, actor: dict, user_id: str) -> UserResponse:
    actor_role = _resolve_role(actor.get("role"))
    stmt = select(User).where(User.id == UUID(user_id))

    if actor_role == Role.ADMIN:
        actor_org_id = actor.get("org_id")
        if not actor_org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        stmt = stmt.where(User.organization_id == UUID(actor_org_id))

    db_user = (await db.execute(stmt)).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(db_user)


async def update_user_by_admin(db: AsyncSession, actor: dict, user_id: str, data: UserUpdate) -> UserResponse:
    actor_user = await _get_actor_user(db, actor)
    actor_role = actor_user.role

    stmt = select(User).where(User.id == UUID(user_id))
    if actor_role == Role.ADMIN:
        if not actor_user.organization_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        stmt = stmt.where(User.organization_id == actor_user.organization_id)

    db_user = (await db.execute(stmt)).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    payload = data.model_dump(exclude_unset=True)

    # Normalize email for uniqueness checks.
    if "email" in payload and payload["email"] is not None:
        payload["email"] = str(payload["email"]).strip().lower()

    if str(db_user.id) == str(actor_user.id) and payload.get("is_active") is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    requested_role = payload.get("role", db_user.role)
    if not _can_manage_user(actor_role, requested_role):
        raise HTTPException(status_code=403, detail="Insufficient permissions for target role")
    if actor_role == Role.ADMIN and db_user.role in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Admins cannot modify admin-level users")

    if actor_role == Role.ADMIN and payload.get("organization_id") and payload["organization_id"] != actor_user.organization_id:
        raise HTTPException(status_code=403, detail="Admins cannot move users across organizations")

    requested_org_id = payload.get("organization_id", db_user.organization_id)
    if requested_role == Role.ADMIN and requested_org_id is None:
        raise HTTPException(status_code=400, detail="Admin must be assigned to one organization")

    await _ensure_organization_exists(db, requested_org_id)

    if payload.get("email") and payload["email"] != db_user.email:
        existing = (await db.execute(select(User).where(User.email == payload["email"]))).scalar_one_or_none()
        if existing and str(existing.id) != str(db_user.id):
            raise HTTPException(status_code=409, detail="Email already registered")

    for field, value in payload.items():
        if hasattr(db_user, field):
            setattr(db_user, field, value)

    await db.flush()
    await db.refresh(db_user)
    return UserResponse.model_validate(db_user)


async def deactivate_user_by_admin(db: AsyncSession, actor: dict, user_id: str) -> UserResponse:
    updated = await update_user_by_admin(db, actor, user_id, UserUpdate(is_active=False))
    return updated


async def update_user_password_by_admin(db: AsyncSession, actor: dict, user_id: str, new_password: str) -> UserResponse:
    actor_user = await _get_actor_user(db, actor)
    actor_role = actor_user.role

    stmt = select(User).where(User.id == UUID(user_id))
    if actor_role == Role.ADMIN:
        if not actor_user.organization_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        stmt = stmt.where(User.organization_id == actor_user.organization_id)

    db_user = (await db.execute(stmt)).scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not _can_manage_user(actor_role, db_user.role):
        raise HTTPException(status_code=403, detail="Insufficient permissions for target role")
    if actor_role == Role.ADMIN and db_user.role in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise HTTPException(status_code=403, detail="Admins cannot modify admin-level users")

    db_user.hashed_password = hash_password(new_password)
    await db.flush()
    await db.refresh(db_user)
    return UserResponse.model_validate(db_user)


async def list_organizations_for_actor(db: AsyncSession, actor: dict) -> list[OrganizationResponse]:
    actor_role = _resolve_role(actor.get("role"))
    stmt = select(Organization)

    if actor_role == Role.ADMIN:
        actor_org_id = actor.get("org_id")
        if not actor_org_id:
            raise HTTPException(status_code=400, detail="Organization context required")
        stmt = stmt.where(Organization.id == UUID(actor_org_id))

    orgs = (await db.execute(stmt)).scalars().all()
    return [OrganizationResponse.model_validate(o) for o in orgs]


async def get_organization_for_actor(db: AsyncSession, actor: dict, org_id: str) -> OrganizationResponse:
    actor_role = _resolve_role(actor.get("role"))
    target_id = UUID(org_id)

    if actor_role == Role.ADMIN and actor.get("org_id") != str(target_id):
        raise HTTPException(status_code=403, detail="Admins can only access their organization")

    org = (await db.execute(select(Organization).where(Organization.id == target_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationResponse.model_validate(org)


async def update_organization_by_owner(
    db: AsyncSession,
    actor: dict,
    org_id: str,
    data: OrganizationUpdate,
) -> OrganizationResponse:
    actor_role = _resolve_role(actor.get("role"))
    target_id = UUID(org_id)
    if actor_role == Role.ADMIN and actor.get("org_id") != str(target_id):
        raise HTTPException(status_code=403, detail="Admins can only update their organization")

    org = (await db.execute(select(Organization).where(Organization.id == target_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    payload = data.model_dump(exclude_unset=True)
    if payload.get("slug"):
        existing = (
            await db.execute(select(Organization).where(Organization.slug == payload["slug"], Organization.id != target_id))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Organization slug already exists")

    for field, value in payload.items():
        if hasattr(org, field):
            setattr(org, field, value)

    await db.flush()
    await db.refresh(org)
    return OrganizationResponse.model_validate(org)


async def deactivate_organization_by_owner(db: AsyncSession, actor: dict, org_id: str) -> OrganizationResponse:
    org = await update_organization_by_owner(db, actor, org_id, OrganizationUpdate(is_active=False))
    target_id = UUID(org_id)
    users = (await db.execute(select(User).where(User.organization_id == target_id))).scalars().all()
    for user in users:
        if user.role in {Role.ADMIN, Role.SUPER_ADMIN}:
            continue
        user.is_active = False
    await db.flush()
    return org


async def login_user(db: AsyncSession, data: LoginRequest) -> LoginResponse:
    """Authenticate user and return tokens."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    if _is_expired(user.expires_at):
        raise HTTPException(status_code=403, detail="Account expired")

    if user.role != Role.SUPER_ADMIN and user.organization_id:
        org = (await db.execute(select(Organization).where(Organization.id == user.organization_id))).scalar_one_or_none()
        if org and (not org.is_active or _is_expired(org.expires_at)):
            raise HTTPException(status_code=403, detail="Organization is inactive or expired")

    # Update last login
    user.last_login = datetime.now(timezone.utc)

    # Generate tokens
    org_id = str(user.organization_id) if user.organization_id else None
    access_token, access_jti, expires_in = create_access_token(str(user.id), user.role, org_id)
    refresh_token, refresh_jti = create_refresh_token(str(user.id))

    get_runtime_cache().set_session(
        str(user.id),
        {
            "access_jti": access_jti,
            "refresh_jti": refresh_jti,
            "role": user.role.value,
            "org_id": org_id or "",
        },
        ttl_seconds=7 * 24 * 3600,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenRefreshResponse:
    """Validate refresh token and issue new token pair."""
    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user_id = payload["sub"]
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    if _is_expired(user.expires_at):
        raise HTTPException(status_code=401, detail="User account expired")

    if user.role != Role.SUPER_ADMIN and user.organization_id:
        org = (await db.execute(select(Organization).where(Organization.id == user.organization_id))).scalar_one_or_none()
        if org and (not org.is_active or _is_expired(org.expires_at)):
            raise HTTPException(status_code=401, detail="Organization is inactive or expired")

    # Blacklist old refresh token
    old_jti = payload.get("jti")
    if old_jti:
        get_runtime_cache().blacklist_token(old_jti, 7 * 24 * 3600)

    org_id = str(user.organization_id) if user.organization_id else None
    new_access, _, expires_in = create_access_token(str(user.id), user.role, org_id)
    new_refresh, _ = create_refresh_token(str(user.id))

    return TokenRefreshResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=expires_in,
    )


async def logout_user(user_id: str, jti: str | None) -> None:
    """Blacklist current token and clear session."""
    cache = get_runtime_cache()
    if jti:
        cache.blacklist_token(jti, 24 * 3600)
    cache.clear_session(user_id)

