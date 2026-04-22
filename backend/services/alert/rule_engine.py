"""
Alert Rule Engine
==================
Evaluates telemetry data against configured alert rules.
Supports conditions like:
  {"field": "battery.remaining", "operator": "lt", "value": 20}
  {"field": "gps.fix_type", "operator": "eq", "value": 0}
  {"field": "altitude", "operator": "gt", "value": 120}
"""
from __future__ import annotations

import logging
import math

from backend.shared.schemas.alert import GeofenceZone
from backend.shared.schemas.telemetry import TelemetryFrame

logger = logging.getLogger(__name__)


OPERATORS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
}


def evaluate_condition(telemetry: TelemetryFrame, condition: dict) -> bool:
    """Evaluate a single alert condition against a telemetry frame."""
    field_path = condition.get("field", "")
    operator = condition.get("operator", "eq")
    threshold = condition.get("value")

    # Navigate nested fields (e.g., "battery.remaining")
    value = _get_nested_field(telemetry, field_path)
    if value is None:
        return False

    op_func = OPERATORS.get(operator)
    if not op_func:
        logger.warning(f"Unknown operator: {operator}")
        return False

    try:
        return op_func(float(value), float(threshold))
    except (ValueError, TypeError):
        return False


def _get_nested_field(obj, path: str):
    """Navigate dot-separated field path on a Pydantic model."""
    parts = path.split(".")
    current = obj
    for part in parts:
        if hasattr(current, part):
            current = getattr(current, part)
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def check_geofence(lat: float, lng: float, alt: float, zone: GeofenceZone) -> bool:
    """
    Check if a position violates a geofence zone.
    Returns True if OUTSIDE allowed zone (violation).
    """
    if zone.type == "circle":
        if not zone.coordinates or not zone.radius:
            return False
        center_lat, center_lng = zone.coordinates[0]
        distance = _haversine(lat, lng, center_lat, center_lng)
        if distance > zone.radius:
            return True
    elif zone.type == "polygon":
        if not _point_in_polygon(lat, lng, zone.coordinates):
            return True

    # Altitude checks
    if zone.max_altitude is not None and alt > zone.max_altitude:
        return True
    if zone.min_altitude is not None and alt < zone.min_altitude:
        return True

    return False


def _point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    """Ray-casting algorithm for point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

