"""SQLAlchemy ORM models for alerts and geofence zones."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.shared.database.postgres import PostgresBase
from backend.shared.schemas.alert import AlertCategory, AlertSeverity


class Alert(PostgresBase):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, name="alert_severity"), nullable=False)
    category: Mapped[AlertCategory] = mapped_column(Enum(AlertCategory, name="alert_category"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class GeofenceZoneRecord(PostgresBase):
    __tablename__ = "geofence_zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="polygon")
    coordinates: Mapped[list] = mapped_column(JSON, nullable=False)
    radius: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    action: Mapped[str] = mapped_column(String(20), default="alert")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AlertRuleRecord(PostgresBase):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[AlertCategory] = mapped_column(Enum(AlertCategory, name="alert_category_rule"), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity, name="alert_severity_rule"), nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    notification_channels: Mapped[list] = mapped_column(JSON, default=list)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

