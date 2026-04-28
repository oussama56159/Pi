"""
AeroCommand MQTT Topic Architecture
====================================
All MQTT topics follow the pattern:
    aerocommand/{org_id}/{domain}/{vehicle_id}/{sub_topic}

Topic Hierarchy:
    aerocommand/
    ├── {org_id}/
    │   ├── telemetry/
    │   │   ├── {vehicle_id}/raw          # Raw MAVLink telemetry from edge
    │   │   ├── {vehicle_id}/processed    # Processed telemetry (cloud → dashboard)
    │   │   └── {vehicle_id}/heartbeat    # Heartbeat (1 Hz)
    │   ├── command/
    │   │   ├── {vehicle_id}/request      # Command from cloud → edge
    │   │   ├── {vehicle_id}/ack          # Command acknowledgment edge → cloud
    │   │   └── {vehicle_id}/response     # Command result edge → cloud
    │   ├── mission/
    │   │   ├── {vehicle_id}/upload       # Mission upload cloud → edge
    │   │   ├── {vehicle_id}/download/request   # Mission download request cloud → edge
    │   │   ├── {vehicle_id}/download/response  # Mission download response edge → cloud
    │   │   ├── {vehicle_id}/progress     # Mission progress edge → cloud
    │   │   └── {vehicle_id}/status       # Mission status changes
    │   ├── alert/
    │   │   ├── {vehicle_id}/geofence     # Geofence violation alerts
    │   │   ├── {vehicle_id}/battery      # Battery critical alerts
    │   │   └── {vehicle_id}/system       # System alerts (connection, firmware)
    │   ├── status/
    │   │   ├── {vehicle_id}/online       # Vehicle online/offline (LWT)
    │   │   └── {vehicle_id}/mode         # Flight mode changes
    │   └── system/
    │       ├── broadcast                 # System-wide broadcasts
    │       └── health                    # Platform health
"""


class MQTTTopics:
    """Centralized MQTT topic builder for the AeroCommand platform."""

    ROOT = "aerocommand"

    # ── Telemetry ──
    @staticmethod
    def telemetry_raw(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/telemetry/{vehicle_id}/raw"

    @staticmethod
    def telemetry_processed(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/telemetry/{vehicle_id}/processed"

    @staticmethod
    def heartbeat(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/telemetry/{vehicle_id}/heartbeat"

    # ── Commands ──
    @staticmethod
    def command_request(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/command/{vehicle_id}/request"

    @staticmethod
    def command_ack(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/command/{vehicle_id}/ack"

    @staticmethod
    def command_response(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/command/{vehicle_id}/response"

    # ── Missions ──
    @staticmethod
    def mission_upload(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/mission/{vehicle_id}/upload"

    @staticmethod
    def mission_download_request(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/mission/{vehicle_id}/download/request"

    @staticmethod
    def mission_download_response(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/mission/{vehicle_id}/download/response"

    @staticmethod
    def mission_progress(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/mission/{vehicle_id}/progress"

    @staticmethod
    def mission_status(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/mission/{vehicle_id}/status"

    # ── Alerts ──
    @staticmethod
    def alert_geofence(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/alert/{vehicle_id}/geofence"

    @staticmethod
    def alert_battery(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/alert/{vehicle_id}/battery"

    @staticmethod
    def alert_system(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/alert/{vehicle_id}/system"

    # ── Status (LWT) ──
    @staticmethod
    def status_online(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/status/{vehicle_id}/online"

    @staticmethod
    def status_mode(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/status/{vehicle_id}/mode"

    # ── System ──
    @staticmethod
    def system_broadcast(org_id: str) -> str:
        return f"aerocommand/{org_id}/system/broadcast"

    @staticmethod
    def system_health() -> str:
        return "aerocommand/$SYS/health"

    @staticmethod
    def system_reconcile_request(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/system/{vehicle_id}/reconcile/request"

    @staticmethod
    def system_reconcile_response(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/system/{vehicle_id}/reconcile/response"

    # ── Wildcard subscriptions ──
    @staticmethod
    def all_telemetry(org_id: str) -> str:
        return f"aerocommand/{org_id}/telemetry/+/raw"

    @staticmethod
    def all_heartbeats(org_id: str) -> str:
        return f"aerocommand/{org_id}/telemetry/+/heartbeat"

    @staticmethod
    def all_alerts(org_id: str) -> str:
        return f"aerocommand/{org_id}/alert/#"

    @staticmethod
    def all_vehicle_topics(org_id: str, vehicle_id: str) -> str:
        return f"aerocommand/{org_id}/+/{vehicle_id}/#"

