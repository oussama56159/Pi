"""SQLAlchemy models for telemetry history stored in PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.database.postgres import PostgresBase


class TelemetryHistoryRecord(PostgresBase):
    __tablename__ = "telemetry_history"
    __table_args__ = (
        Index("ix_telemetry_history_vehicle_timestamp", "vehicle_id", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)