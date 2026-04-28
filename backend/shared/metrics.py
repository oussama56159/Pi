from __future__ import annotations

from prometheus_client import Counter, Histogram

COMMAND_DISPATCH_TOTAL = Counter(
    "aero_command_dispatch_total",
    "Total command dispatch attempts",
    ["command", "result"],
)

MISSION_UPLOAD_TOTAL = Counter(
    "aero_mission_upload_total",
    "Total mission upload requests",
    ["result"],
)

MISSION_DOWNLOAD_TOTAL = Counter(
    "aero_mission_download_total",
    "Total mission download requests",
    ["result"],
)

MQTT_PUBLISH_LATENCY_SECONDS = Histogram(
    "aero_mqtt_publish_latency_seconds",
    "Latency of MQTT publish operations",
    ["topic_group"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

