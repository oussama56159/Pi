"""PostgreSQL async engine & session factory using SQLAlchemy 2.0."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.shared.config import get_base_settings

_engine = None
_session_factory = None


class PostgresBase(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def init_postgres() -> None:
    """Initialize the async engine and session factory."""
    global _engine, _session_factory
    settings = get_base_settings()
    _engine = create_async_engine(
        settings.postgres_dsn,
        echo=settings.DEBUG,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency – yields an async session."""
    if _session_factory is None:
        await init_postgres()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_direct_postgres_session() -> AsyncSession:
    """Create an async session without auto-commit dependency behavior."""
    if _session_factory is None:
        await init_postgres()
    return _session_factory()


async def ensure_schema() -> None:
    """Create all tables for local/dev when migrations are not applied."""
    if _engine is None:
        await init_postgres()

    # Import models so they register with PostgresBase.metadata
    from backend.services.auth import models as _auth_models  # noqa: F401
    from backend.services.fleet import models as _fleet_models  # noqa: F401
    from backend.services.mission import models as _mission_models  # noqa: F401
    from backend.services.command import models as _command_models  # noqa: F401
    from backend.services.alert import models as _alert_models  # noqa: F401
    from backend.services.telemetry import models as _telemetry_models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(PostgresBase.metadata.create_all)

