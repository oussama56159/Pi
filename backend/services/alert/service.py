"""Alert business logic – CRUD, rule evaluation, notification dispatch."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.schemas.alert import (
    AlertCategory,
    AlertCreate,
    AlertResponse,
    AlertSeverity,
    GeofenceZone,
)
from backend.shared.schemas.telemetry import TelemetryFrame

from .models import Alert, AlertRuleRecord, GeofenceZoneRecord
from .rule_engine import check_geofence, evaluate_condition

logger = logging.getLogger(__name__)


async def create_alert(db: AsyncSession, org_id: UUID, data: AlertCreate) -> AlertResponse:
    alert = Alert(
        vehicle_id=data.vehicle_id,
        organization_id=org_id,
        severity=data.severity,
        category=data.category,
        title=data.title,
        message=data.message,
        metadata_json=data.metadata,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


async def _rule_alert_in_cooldown(
    db: AsyncSession,
    org_id: UUID,
    vehicle_id: UUID,
    rule_id: UUID,
    cooldown_seconds: int,
) -> bool:
    if cooldown_seconds <= 0:
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=int(cooldown_seconds))
    result = await db.execute(
        select(Alert.id).where(
            Alert.organization_id == org_id,
            Alert.vehicle_id == vehicle_id,
            Alert.created_at >= cutoff,
            Alert.metadata_json["rule_id"].as_string() == str(rule_id),
        ).order_by(Alert.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def list_alerts(
    db: AsyncSession, org_id: UUID, severity: AlertSeverity | None = None,
    category: AlertCategory | None = None, acknowledged: bool | None = None,
    limit: int = 100,
) -> list[AlertResponse]:
    query = select(Alert).where(Alert.organization_id == org_id)
    if severity:
        query = query.where(Alert.severity == severity)
    if category:
        query = query.where(Alert.category == category)
    if acknowledged is not None:
        query = query.where(Alert.acknowledged == acknowledged)
    query = query.order_by(Alert.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return [AlertResponse.model_validate(a) for a in result.scalars().all()]


async def acknowledge_alert(db: AsyncSession, org_id: UUID, alert_id: UUID, user_id: UUID) -> AlertResponse:
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.organization_id == org_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    alert.acknowledged_by = user_id
    alert.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


async def resolve_alert(db: AsyncSession, org_id: UUID, alert_id: UUID) -> AlertResponse:
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.organization_id == org_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


async def evaluate_telemetry_against_rules(
    db: AsyncSession, org_id: UUID, telemetry: TelemetryFrame,
) -> list[AlertCreate]:
    """Evaluate incoming telemetry against all active alert rules."""
    triggered_alerts: list[AlertCreate] = []

    try:
        vehicle_uuid = UUID(telemetry.vehicle_id) if telemetry.vehicle_id else None
    except Exception:
        vehicle_uuid = None

    # Fetch active rules
    result = await db.execute(
        select(AlertRuleRecord).where(
            AlertRuleRecord.organization_id == org_id,
            AlertRuleRecord.enabled == True,
        )
    )
    rules = result.scalars().all()

    for rule in rules:
        if evaluate_condition(telemetry, rule.condition):
            if vehicle_uuid is not None and await _rule_alert_in_cooldown(
                db,
                org_id,
                vehicle_uuid,
                rule.id,
                rule.cooldown_seconds,
            ):
                continue
            triggered_alerts.append(AlertCreate(
                vehicle_id=UUID(telemetry.vehicle_id) if telemetry.vehicle_id else None,
                severity=rule.severity,
                category=rule.category,
                title=f"Rule triggered: {rule.name}",
                message=f"Condition met: {rule.condition}",
                metadata={"rule_id": str(rule.id), "telemetry_seq": telemetry.seq},
            ))

    # Check geofences
    result = await db.execute(
        select(GeofenceZoneRecord).where(
            GeofenceZoneRecord.organization_id == org_id,
            GeofenceZoneRecord.enabled == True,
        )
    )
    zones = result.scalars().all()

    for zone_record in zones:
        zone = GeofenceZone(
            id=zone_record.id, name=zone_record.name, type=zone_record.type,
            coordinates=zone_record.coordinates, radius=zone_record.radius,
            max_altitude=zone_record.max_altitude, min_altitude=zone_record.min_altitude,
            action=zone_record.action,
        )
        if check_geofence(telemetry.gps.lat, telemetry.gps.lng, telemetry.gps.alt, zone):
            triggered_alerts.append(AlertCreate(
                vehicle_id=UUID(telemetry.vehicle_id) if telemetry.vehicle_id else None,
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.GEOFENCE,
                title=f"Geofence violation: {zone.name}",
                message=f"Vehicle exited zone '{zone.name}' at ({telemetry.gps.lat}, {telemetry.gps.lng})",
                metadata={"zone_id": str(zone.id), "action": zone.action},
            ))

    return triggered_alerts

