"""Add command idempotency columns and uniqueness.

Revision ID: 20260425_command_idempotency_and_safety_state
Revises: 20260421_telemetry_history_postgres
Create Date: 2026-04-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260425_command_idempotency_and_safety_state"
down_revision = "20260421_telemetry_history_postgres"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commands", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("commands", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))

    # Backfill existing rows with deterministic placeholders.
    op.execute(
        "UPDATE commands SET idempotency_key = CONCAT('legacy-', id::text) WHERE idempotency_key IS NULL"
    )
    op.execute(
        "UPDATE commands SET request_fingerprint = md5(COALESCE(params::text, '') || command::text || vehicle_id::text) "
        "WHERE request_fingerprint IS NULL"
    )

    op.alter_column("commands", "idempotency_key", nullable=False)
    op.alter_column("commands", "request_fingerprint", nullable=False)
    op.create_unique_constraint("uq_command_org_idempotency", "commands", ["organization_id", "idempotency_key"])
    op.create_index("ix_commands_idempotency_key", "commands", ["idempotency_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_commands_idempotency_key", table_name="commands")
    op.drop_constraint("uq_command_org_idempotency", "commands", type_="unique")
    op.drop_column("commands", "request_fingerprint")
    op.drop_column("commands", "idempotency_key")

