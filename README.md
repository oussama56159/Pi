# AeroCommand

AeroCommand is a cloud-plus-edge platform for operating autonomous drone and robot fleets.

It combines:
- A FastAPI backend with MQTT ingestion and WebSocket fanout
- A React dashboard for operations and administration
- A Flutter mobile client for field operators
- A Python edge agent running near the vehicle (MAVLink <-> MQTT bridge)

## Project Overview

Primary capabilities:
- Real-time telemetry ingestion from edge devices
- Fleet and user/organization management (RBAC)
- Mission planning, assignment, upload/download, and progress tracking
- Command dispatch and ACK/result pipeline
- Alert ingestion, rules, acknowledgment, and streaming to clients

Current architecture is monolith-style API routing in one service process (`backend/services/gateway/main.py`) with domain modules mounted under `/api/v1`.

## Architecture (Text Diagram)

```text
Pixhawk / vehicle bus
  -> MAVLink (serial/udp/tcp)
  -> edge-agent (Python, pymavlink)
  -> MQTT publish to EMQX (telemetry, heartbeat, mission/status, command ACK)
  -> backend MQTT listeners (telemetry/mission/command/alert)
  -> PostgreSQL + in-memory runtime cache
  -> WebSocket push (org/vehicle/alerts channels)
  -> Dashboard (React) and Mobile (Flutter)

Client actions (web/mobile)
  -> REST API (FastAPI)
  -> DB writes + MQTT publishes (command/mission upload)
  -> edge-agent subscriptions
  -> autopilot execution + ACK/status back to cloud
```

## Repository Layout

Top-level directories:
- `backend/`: FastAPI gateway and domain services (`auth`, `fleet`, `telemetry`, `mission`, `command`, `alert`)
- `dashboard/`: React + Vite SPA
- `mobile/`: Flutter app
- `edge-agent/`: Python edge runtime for MAVLink + camera stream + MQTT bridge
- `shared_python/`: shared Python schemas/topics/config used by backend and edge-agent
- `infra/`: EMQX config, K8s manifests, Helm chart
- `scripts/`: PowerShell helper scripts for local operations
- `testMQTT/`: drone/robot simulators for local MQTT testing
- `models/`: model notes/documentation

## Module Interaction Map

Backend internal flow:
- `backend/services/gateway/main.py`: app lifecycle, middleware, MQTT listeners startup
- `backend/services/gateway/routes/proxy.py`: mounts service routers
- `backend/services/telemetry/mqtt_listener.py`: subscribes to telemetry topics
- `backend/services/telemetry/service.py`: validates frame, stores history, updates cache + vehicle state, broadcasts WebSocket
- `backend/services/mission/mqtt_listener.py`: mission status/progress updates from edge
- `backend/services/command/mqtt_listener.py`: consumes command ACK/response from edge
- `backend/services/alert/mqtt_listener.py`: consumes alert messages and broadcasts alerts stream

Shared runtime components:
- `backend/shared/mqtt_runtime.py`: shared MQTT connection + subscriptions
- `backend/shared/runtime_cache.py`: in-memory snapshots/rate-limit/session/audit cache
- `backend/shared/database/postgres.py`: async engine/session/schema bootstrap helpers

Frontend interaction:
- Dashboard API clients in `dashboard/src/lib/api/*`
- Dashboard WebSocket hooks in `dashboard/src/lib/websocket/*`
- Dashboard pages under `dashboard/src/pages/*`

Mobile interaction:
- HTTP layer in `mobile/aerocommand_mobile/lib/src/api/*`
- WebSocket + local history in `mobile/aerocommand_mobile/lib/src/realtime/realtime_controller.dart`
- App screens/tabs in `mobile/aerocommand_mobile/lib/src/ui/*`

Edge interaction:
- `edge-agent/src/aerocommand_edge_agent/main.py`: orchestrates readers, MQTT bridge, handlers
- `edge-agent/src/aerocommand_edge_agent/mqtt_bridge.py`: MQTT publish/subscribe bridging
- `edge-agent/src/aerocommand_edge_agent/mavlink_reader.py`: MAVLink read/wait primitives

## Runtime Data Flows

Telemetry flow:
1. Edge publishes `aerocommand/{org}/telemetry/{vehicle}/raw`
2. Backend validates with Pydantic (`TelemetryFrame`)
3. Stores row in `telemetry_history` (PostgreSQL)
4. Updates runtime cache + vehicle live status fields
5. Broadcasts to WebSocket channels (`vehicle:*`, `org:*`)

Mission flow:
1. Operator creates mission and assignments via REST
2. Upload request published to `aerocommand/{org}/mission/{vehicle}/upload`
3. Edge uploads to autopilot, publishes status/progress
4. Backend updates assignment/progress and pushes WebSocket mission events

Command flow:
1. Client sends command through REST
2. Backend publishes to `aerocommand/{org}/command/{vehicle}/request`
3. Edge executes MAVLink command and publishes ACK/response
4. Backend persists/propagates command state

Alert flow:
1. Telemetry rules and/or edge system alerts generate alerts
2. Alerts saved/queryable via `/api/v1/alerts`
3. Alert stream broadcast over WebSocket `alerts:{org}`

## Technology Stack

- Backend: Python 3.11, FastAPI, SQLAlchemy async, Pydantic, aiomqtt
- Data: PostgreSQL (history + relational state), in-memory process cache
- Messaging: EMQX (MQTT)
- Dashboard: React 18, Vite, Zustand, Recharts, Leaflet
- Mobile: Flutter, Provider, flutter_map
- Edge: Python, pymavlink, aiomqtt, optional OpenCV camera stream
- Deployment: Docker Compose, Kubernetes manifests, Helm, GitHub Actions

## Local Development Setup

### Option A: Docker Compose (Recommended)

Prerequisites:
- Docker Desktop

From repository root:

```bash
docker compose up -d --build
```

Default endpoints:
- Dashboard: `http://localhost:3000`
- API: `http://localhost:8000`
- API docs (debug): `http://localhost:8000/docs`
- EMQX dashboard: `http://localhost:18083`

Default dev owner credentials:
- Email: `owner@makerskills.com`
- Password: `makerskills_owner_change_me`

Windows helper scripts:
- `scripts/start-dev.ps1`
- `scripts/stop-dev.ps1`
- `scripts/restart-dev.ps1`
- `scripts/get-uuids.ps1`

### Option B: Run services individually

Prerequisites:
- Python 3.11+
- Node.js 20+
- PostgreSQL
- EMQX

Backend:

```bash
cd backend
pip install -U pip
pip install fastapi[standard] uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic \
  pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] \
  aiomqtt httpx python-multipart orjson
uvicorn backend.services.gateway.main:app --reload --port 8000
```

Dashboard:

```bash
cd dashboard
npm ci
npm run dev
```

Mobile:

```bash
cd mobile/aerocommand_mobile
flutter pub get
flutter run
```

Edge-agent (editable install):

```bash
pip install -e ./shared_python
pip install -e ./edge-agent
```

## Environment Variables

### Backend (`backend/shared/config.py` + compose)

Core:
- `ENVIRONMENT` (`development|staging|production`)
- `DEBUG`
- `AUTO_CREATE_DB`

PostgreSQL:
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`

MQTT:
- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_CLIENT_ID_PREFIX`
- `MQTT_QOS`

Auth:
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`
- `JWT_REFRESH_TOKEN_EXPIRE_DAYS`

CORS:
- `CORS_ORIGINS`
- `CORS_ORIGIN_REGEX`

Owner seeding:
- `SEED_OWNER_ENABLED`
- `OWNER_EMAIL`
- `OWNER_PASSWORD`
- `OWNER_NAME`
- `OWNER_CREATE_ORG`
- `OWNER_ORG_NAME`
- `OWNER_ORG_SLUG`

SMTP/password recovery:
- `SUPPORT_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`
- `SMTP_USE_STARTTLS`
- `SMTP_USE_SSL`

### Dashboard (`dashboard/.env.example`)

- `VITE_API_BASE_URL`
- `VITE_WS_BASE_URL`
- `VITE_TELEMETRY_WS_URL`
- `VITE_MQTT_BROKER_URL`
- `VITE_MOCK_MODE`
- `VITE_APP_TITLE`
- `VITE_SUPPORT_EMAIL`

### Edge Agent (`edge-agent/src/aerocommand_edge_agent/config.py`)

Identity:
- `ORG_ID`
- `VEHICLE_ID`

MAVLink:
- `MAVLINK_CONNECTION`
- `MAVLINK_BAUD`
- `MAVLINK_SOURCE_SYSTEM`

MQTT:
- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_CLIENT_ID`
- `MQTT_KEEPALIVE`
- `MQTT_QOS`

Rates:
- `TELEMETRY_HZ`
- `HEARTBEAT_HZ`

Battery fallback:
- `BATTERY_VOLTAGE_EMPTY`
- `BATTERY_VOLTAGE_FULL`

Camera stream:
- `CAMERA_STREAM_ENABLED`
- `CAMERA_STREAM_HOST`
- `CAMERA_STREAM_PORT`
- `CAMERA_STREAM_PATH`
- `CAMERA_STREAM_CAMERA_INDEX`
- `CAMERA_STREAM_FRAME_WIDTH`
- `CAMERA_STREAM_FRAME_HEIGHT`
- `CAMERA_STREAM_FPS`
- `CAMERA_STREAM_JPEG_QUALITY`
- `CAMERA_STREAM_TOKEN`
- `CAMERA_STREAM_PUBLIC_URL`
- `DRONE_IP`

## API and System Surface

Primary REST prefixes (mounted under `/api/v1`):
- `/auth`
- `/fleet`
- `/telemetry`
- `/missions`
- `/commands`
- `/alerts`
- `/vision`
- `/actions`

WebSocket endpoint:
- `/api/v1/telemetry/ws?channels=org:{org},alerts:{org}`

Health endpoints:
- `/health`
- `/health/live`
- `/health/ready`

## YOLOv8 Video Analytics (Backend CPU)

The platform now supports backend-side YOLOv8 inference for camera streams coming from edge devices.

Flow:
1. Configure a camera stream URL per vehicle in the dashboard Camera page.
2. Start YOLO analytics from the Camera page.
3. The backend ingests the stream, runs YOLOv8 (`person`, `dog`, `sheep`, `cow`), and exposes an annotated MJPEG stream.
4. The dashboard renders the annotated stream with bounding boxes and detection counts.

Vision endpoints (`/api/v1/vision`):
- `POST /streams/{vehicle_id}/start`
- `POST /streams/{vehicle_id}/stop`
- `GET /streams/{vehicle_id}/annotated.mjpg`
- `GET /streams/{vehicle_id}/detections/latest`

Backend vision settings (in `backend/shared/config.py`):
- `VISION_ENABLED`
- `VISION_MODEL_NAME` (default `yolov8n.pt`)
- `VISION_CONFIDENCE_THRESHOLD`
- `VISION_ALLOWED_CLASSES` (default `person,dog,sheep,cow`)
- `VISION_FRAME_SKIP`
- `VISION_OUTPUT_FPS`
- `VISION_MAX_WIDTH`

## Deployment

### Production Compose

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Kubernetes Manifests

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/secrets.yaml
kubectl apply -f infra/k8s/databases.yaml
kubectl apply -f infra/k8s/emqx.yaml
kubectl apply -f infra/k8s/api-server.yaml
kubectl apply -f infra/k8s/dashboard.yaml
kubectl apply -f infra/k8s/ingress.yaml
```

### Helm

```bash
helm upgrade --install aerocommand ./infra/helm/aerocommand \
  --namespace aerocommand --create-namespace \
  --values ./infra/helm/aerocommand/values.yaml
```

### CI/CD Pipelines

- `.github/workflows/ci.yml`: lint, tests, frontend build, docker build/push to GHCR
- `.github/workflows/cd.yml`: staging/prod deploy and migration job

## Contribution Guide

Recommended contribution workflow:
1. Create a feature branch from `develop`.
2. Keep commits scoped to one concern (backend, dashboard, mobile, edge, infra).
3. Run checks before PR:
   - Backend lint/tests
   - Dashboard lint/build
   - Mobile analyze/tests where relevant
4. Open PR to `develop` with:
   - summary
   - risk notes
   - screenshots or API examples if behavior changed
5. Require green CI before merge.

Conventions:
- Preserve API path prefixes and schema compatibility when possible.
- Keep shared contracts in `shared_python/src/backend/shared/schemas/*` aligned with consumers.
- Do not commit secrets; use env vars or cluster secret stores.

## Known Constraints and Gaps

- `backend/services/vision/` is present as a directory but currently has no tracked implementation files.
- `backend/services/telemetry/mqtt_client.py` exists but runtime path uses shared MQTT runtime listeners instead.
- Some default development secrets are intentionally insecure and must be overridden in production.

## License

Proprietary (project/course context). Consult maintainers before external redistribution.
