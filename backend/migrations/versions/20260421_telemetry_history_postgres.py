"""Add PostgreSQL telemetry history table.

Revision ID: 20260421_telemetry_history_postgres
Revises:
Create Date: 2026-04-21 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260421_telemetry_history_postgres"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telemetry_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_telemetry_history_vehicle_timestamp",
        "telemetry_history",
        ["vehicle_id", "timestamp"],
    )
    op.create_index("ix_telemetry_history_vehicle_id", "telemetry_history", ["vehicle_id"])
    op.create_index("ix_telemetry_history_timestamp", "telemetry_history", ["timestamp"])
    op.create_index("ix_telemetry_history_organization_id", "telemetry_history", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_telemetry_history_organization_id", table_name="telemetry_history")
    op.drop_index("ix_telemetry_history_timestamp", table_name="telemetry_history")
    op.drop_index("ix_telemetry_history_vehicle_id", table_name="telemetry_history")
    op.drop_index("ix_telemetry_history_vehicle_timestamp", table_name="telemetry_history")
    op.drop_table("telemetry_history")