"""
Alembic migration environment.
Imports all ORM models so Alembic can detect schema changes.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.shared.database.postgres import PostgresBase

# Import ALL models so they register with PostgresBase.metadata
from backend.services.alert.models import Alert, AlertRuleRecord, GeofenceZoneRecord  # noqa: F401
from backend.services.auth.models import APIKey, Organization, User  # noqa: F401
from backend.services.command.models import CommandRecord  # noqa: F401
from backend.services.fleet.models import Fleet, FleetUserAssignment, Vehicle  # noqa: F401
from backend.services.mission.models import Mission, MissionAssignment, Waypoint  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = PostgresBase.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

