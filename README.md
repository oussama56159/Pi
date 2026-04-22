# AeroCommand

**AeroCommand** is a full-stack cloud + edge platform for real-time drone and robot fleet management. It connects physical vehicles (via Pixhawk flight controllers and Raspberry Pi edge agents) to a centralized backend, and delivers live telemetry, command & control, mission planning, and alerting through both a **web dashboard** and a **mobile app**.

---

## What it does

- **Real-time telemetry** — Sensor data (GPS, altitude, speed, attitude, battery, battery temperature, etc.) flows from each drone's Pixhawk flight controller over MAVLink to a Raspberry Pi, which publishes it via MQTT to the cloud backend. The backend validates, stores, caches, and broadcasts the data over WebSocket to all connected clients in real time.
- **Fleet management** — Register, organize, and monitor all your drones and robots. Group vehicles into fleets, assign users to fleets, and view live status for every vehicle.
- **Mission planning** — Create waypoint-based missions with a visual planner (map-based), assign missions to vehicles, upload them, and track execution status live.
- **Command & control** — Send commands to vehicles in real time (arm, disarm, takeoff, land, RTL, emergency stop, etc.) from the dashboard or mobile app. Commands are routed through MQTT to the edge agent, which translates them into MAVLink instructions for the Pixhawk.
- **Alerts & rules** — Configurable alert rules trigger on telemetry conditions (low battery, geofence breach, signal loss, etc.). Alerts are pushed in real time to all connected clients and stored for review.
- **Analytics** — Historical telemetry charts, flight hours, mission statistics, and incident reports.
- **Multi-tenant & role-based access** — Organizations, role-based permissions (Super Admin, Admin, Operator, Pilot, Viewer), and user management built in.
- **Mobile app** — A Flutter (Android/iOS) companion app with the same telemetry, fleet, mission, alert, and command features.
- **Edge agent** — A lightweight Python agent that runs on a Raspberry Pi (including Pi Zero), reads MAVLink from a Pixhawk, and bridges telemetry, heartbeat, and mission upload/download traffic to the cloud over MQTT.

---

## Architecture

```
                                    ┌──────────────┐
                                    │  Dashboard   │  React / Vite
                                    │  (Web UI)    │  Real-time charts, map, controls
                                    └──────┬───────┘
                                           │ HTTP + WebSocket
                                           ▼
┌──────────┐    MAVLink     ┌───────────┐  MQTT   ┌──────────────────┐      SQL      ┌──────────────────┐
│ Pixhawk  │──── UART ─────▶│  Pi Zero  │────────▶│  Backend API     │───────────────▶│  PostgreSQL      │
│ (FC)     │   /dev/serial0 │  (Edge    │  EMQX   │  (FastAPI)       │               │  history + state │
│          │                │   Agent)  │◀────────│                  │               │                  │
└──────────┘                └───────────┘ cmds    └──────────────────┘               └──────────────────┘
                                                           │ WebSocket
                                                           ▼
                                                   ┌──────────────┐
                                                   │  Mobile App  │  Flutter (Android/iOS)
                                                   └──────────────┘
```

**Data flow:** Pixhawk sensors → MAVLink (serial) → Raspberry Pi edge agent → MQTT (EMQX broker) → Backend API → WebSocket → Dashboard / Mobile App

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | Python, FastAPI, SQLAlchemy (async), Pydantic |
| **Databases** | PostgreSQL (relational + telemetry history), in-memory cache (latest snapshots / runtime state) |
| **Message broker** | EMQX (MQTT) |
| **Web dashboard** | React 18, Vite, Tailwind CSS, Zustand, Recharts, Leaflet |
| **Mobile app** | Flutter / Dart (Android & iOS) |
| **Edge agent** | Python, pymavlink, aiomqtt |
| **Infrastructure** | Docker Compose, Kubernetes, Helm, GitHub Actions CI/CD |

---

## Repository structure

```
backend/           FastAPI API gateway + service modules (auth, fleet, mission, telemetry, alert, command)
dashboard/         React/Vite web UI
mobile/            Flutter mobile app (Android & iOS)
edge-agent/        Raspberry Pi edge agent (Pixhawk MAVLink ↔ MQTT)
shared_python/     Shared Python library (schemas, MQTT topics, config)
testMQTT/          Drone & robot simulators for local testing without hardware
infra/             Kubernetes manifests, Helm chart, EMQX config
scripts/           PowerShell helper scripts for dev
```

---

## Features by module

### Backend API (`backend/`)

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **Auth** | `/api/v1/auth/*` | JWT login/logout/refresh, user CRUD, organization CRUD, role-based access (Super Admin, Admin, Operator, Pilot, Viewer), password recovery |
| **Fleet** | `/api/v1/fleet/*` | Vehicle CRUD, fleet groups, fleet-user assignments, vehicle status tracking |
| **Telemetry** | `/api/v1/telemetry/*` | Latest snapshot (in-memory), historical queries (PostgreSQL), real-time WebSocket streaming |
| **Missions** | `/api/v1/missions/*` | Mission CRUD, waypoint graph builder, assign/unassign vehicles, upload to vehicle, status tracking |
| **Commands** | `/api/v1/commands/*` | Dispatch commands to vehicles via MQTT (arm, disarm, takeoff, land, RTL, etc.), command history |
| **Alerts** | `/api/v1/alerts/*` | Rule engine, alert CRUD, acknowledge/resolve, real-time push via WebSocket |

### Web Dashboard (`dashboard/`)

- **Dashboard** — Overview with fleet stats, active alerts, recent missions
- **Fleet** — Vehicle list, detail pages with live telemetry cards
- **Live Map** — Real-time vehicle positions on an interactive Leaflet map
- **Telemetry** — Per-vehicle telemetry charts (altitude, speed, battery, etc.) with time range selection and full-screen mode
- **Mission Planner** — Visual waypoint editor on map, mission assignment and execution controls
- **Control Panel** — Direct command interface for pilots (arm, takeoff, land, RTL, emergency stop)
- **Alerts** — Live alert feed with severity filtering, acknowledgement, and resolution
- **Analytics** — Historical charts and statistics
- **User Management** — Admin panel for creating/editing users and organizations
- **Settings** — Notification preferences, telemetry display settings, theme toggle

### Mobile App (`mobile/`)

- Same core features: Dashboard, Fleet, Telemetry, Alerts, Missions
- Real-time WebSocket telemetry streaming
- Dark/light theme
- Demo mode for offline testing
- Profile management

### Edge Agent (`edge-agent/`)

- Reads MAVLink messages from Pixhawk (HEARTBEAT, ATTITUDE, GPS_RAW_INT, GLOBAL_POSITION_INT, SYS_STATUS, BATTERY_STATUS)
- Converts to structured `TelemetryFrame` JSON, including GPS, attitude, battery, and battery temperature when available
- Publishes telemetry and heartbeat to MQTT at configurable rates
- Bridges mission upload and mission download between MQTT and MAVLink
- Receives command requests from MQTT and currently acknowledges them; full MAVLink command execution is still a work item
- Runs as a systemd service on Raspberry Pi

### Simulators (`testMQTT/`)

- `drone_simulator.py` — Simulates a drone with realistic flight physics, GPS movement, battery drain, and link loss
- `robot_simulator.py` — Simulates a ground robot with patrol patterns
- Both support **AeroCommand mode** to publish directly to the backend's MQTT topics (no hardware needed)

---

## Quick start

### Option A: Docker (recommended)

**Prerequisites:** Docker Desktop

```bash
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| EMQX Dashboard | http://localhost:18083 |

**Default login:**
- Email: `owner@makerskills.com`
- Password: `makerskills_owner_change_me`

### Option B: Without Docker

**Prerequisites:** Python 3.11+, Node 20+, PostgreSQL, and EMQX running locally

**Backend:**

```bash
cd backend
pip install -U pip
pip install fastapi[standard] uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic \
  pydantic pydantic-settings python-jose[cryptography] passlib[bcrypt] \
  aiomqtt httpx python-multipart orjson
uvicorn backend.services.gateway.main:app --reload --port 8000
```

**Dashboard:**

```bash
cd dashboard
npm ci
npm run dev
```

Dashboard will be at http://localhost:5173.

### Helper scripts (Windows)

```powershell
./scripts/start-dev.ps1     # Start Docker stack
./scripts/stop-dev.ps1      # Stop Docker stack
./scripts/restart-dev.ps1   # Restart Docker stack
```

---

## Connecting a real drone

Use this flow for a Pixhawk + Raspberry Pi Zero setup:

1. Configure Pixhawk TELEM2 for MAVLink2 at 57600 baud in Mission Planner or QGroundControl.
2. Wire Pixhawk TELEM2 TX, RX, and GND to the Pi UART (`/dev/serial0` on Raspberry Pi OS).
3. Install the shared package and edge agent from the repo root:

```bash
cd shared_python
sudo python3 -m pip install -e . --break-system-packages
cd ../edge-agent
sudo python3 -m pip install -e . --break-system-packages
```

4. Create a vehicle in the dashboard and copy the Vehicle UUID and Organization ID.
5. Put those values into the edge agent env file and point it at your MQTT broker:

```bash
ORG_ID=<your org UUID>
VEHICLE_ID=<your vehicle UUID>
MAVLINK_CONNECTION=/dev/serial0
MAVLINK_BAUD=57600
MQTT_HOST=<your server IP or domain>
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
TELEMETRY_HZ=2
HEARTBEAT_HZ=1
```

6. Start the edge agent and confirm the vehicle goes online in Fleet Management.
7. Verify live GPS, heading, altitude, satellites, voltage, current, and battery temperature in the vehicle detail page.

**Notes:**

- Telemetry and mission upload/download are implemented.
- Command dispatch is still acknowledged by the edge agent but not yet translated into real Pixhawk control commands.

**Test without hardware** using the drone simulator:

```bash
set AEROCOMMAND_ENABLED=true
set AEROCOMMAND_ORG_ID=<your org UUID>
set AEROCOMMAND_VEHICLE_ID=<your vehicle UUID>
python testMQTT/drone_simulator.py
```

For Windows, use the helper script:

```powershell
./scripts/start-drone-sim.ps1 -OrgId <your org UUID> -VehicleId <your vehicle UUID>
```

---

## MQTT topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `aerocommand/{org}/telemetry/{vehicle}/raw` | Edge → Cloud | Telemetry frames |
| `aerocommand/{org}/telemetry/{vehicle}/heartbeat` | Edge → Cloud | Heartbeat pings |
| `aerocommand/{org}/command/{vehicle}/request` | Cloud → Edge | Command dispatch |
| `aerocommand/{org}/command/{vehicle}/ack` | Edge → Cloud | Command acknowledgement |

---

## Deployment

### Production Docker Compose

```bash
docker compose -f docker-compose.prod.yml up -d
```

### Kubernetes

**Raw manifests** (in `infra/k8s/`):

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

**Helm** (chart in `infra/helm/aerocommand/`):

```bash
helm upgrade --install aerocommand ./infra/helm/aerocommand \
  --namespace aerocommand --create-namespace \
  --values ./infra/helm/aerocommand/values.yaml
```

### CI/CD (GitHub Actions)

- `.github/workflows/ci.yml` — Lint, test, build, push Docker images to GHCR
- `.github/workflows/cd.yml` — Deploy to staging/production via Helm

---

## Security model

- Public registration is disabled
- A single owner account is seeded on first startup (configurable via environment variables)
- Owner creates organizations and admin users
- Role-based access: **Super Admin** > **Admin** > **Operator** > **Pilot** > **Viewer**
- JWT-based authentication with access + refresh tokens
- Rate limiting and CORS middleware

**Default dev owner credentials:**

| Setting | Default | Env var |
|---------|---------|---------|
| Email | `owner@makerskills.com` | `OWNER_EMAIL` |
| Password | `makerskills_owner_change_me` | `OWNER_PASSWORD` |
| Name | `MakerSkills Owner` | `OWNER_NAME` |

---

## License

This project was built as a university/group project (PI Group).
