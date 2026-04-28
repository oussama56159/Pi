# AeroCommand Edge Agent (Raspberry Pi)

This agent runs on a Raspberry Pi (or any Linux host) connected to a Pixhawk/autopilot.
It bridges **MAVLink telemetry** to **cloud MQTT** and listens for **cloud commands**.
It can also host an MJPEG camera stream directly inside the agent process.

## What it does

- Reads MAVLink messages from Pixhawk (`SERIAL`, `UDP`, or `TCP`)
- Publishes telemetry frames to MQTT topic:
  - `aerocommand/{org_id}/telemetry/{vehicle_id}/raw`
- Publishes heartbeat to:
  - `aerocommand/{org_id}/telemetry/{vehicle_id}/heartbeat`
- Subscribes to command requests:
  - `aerocommand/{org_id}/command/{vehicle_id}/request`
- Responds with acknowledgements:
  - `aerocommand/{org_id}/command/{vehicle_id}/ack`
- Serves an MJPEG camera stream from the attached USB camera at:
  - `http://<drone-ip>:5000/video`
- Publishes the derived camera stream URL in the heartbeat payload when `DRONE_IP` is set.

## Backend YOLOv8 integration

When using backend-side analytics, keep the edge MJPEG stream enabled and reachable by the backend.

- Edge continues to expose the camera stream (for example `http://<drone-ip>:5000/video`).
- In the dashboard Camera page, set this stream URL and press **Start YOLO**.
- The backend then performs inference and serves an annotated stream to the dashboard.

## Install (dev)

From repo root:

```bash
pip install -e ./shared_python
pip install -e ./edge-agent
# Or, if you want the camera stream and OpenCV support:
# pip install -e "./edge-agent[camera]"
```

## Run

Set environment variables (example):

```bash
export ORG_ID="demo"
export VEHICLE_ID="vehicle-01"
export MAVLINK_CONNECTION="/dev/ttyAMA0"
export MAVLINK_BAUD="57600"
export MQTT_HOST="localhost"
export MQTT_PORT="1883"
export DRONE_IP="192.168.1.42"

# Camera stream (defaults match the old standalone script)
export CAMERA_STREAM_ENABLED="true"
export CAMERA_STREAM_PORT="5000"
export CAMERA_STREAM_PATH="/video"
export CAMERA_STREAM_CAMERA_INDEX="0"
export CAMERA_STREAM_FRAME_WIDTH="640"
export CAMERA_STREAM_FRAME_HEIGHT="480"
export CAMERA_STREAM_FPS="30"

# Optional: override the URL advertised in the heartbeat payload.
# export CAMERA_STREAM_PUBLIC_URL="http://192.168.1.42:5000/video"
```

Run:

```bash
aerocommand-edge-agent
```

## Notes

- For Raspberry Pi serial access, add your user to `dialout` and ensure UART is enabled.
- Command execution is implemented for MAVLink `COMMAND_LONG` payloads produced by the backend.
  The agent sends the command to the autopilot and publishes `COMMAND_ACK` results back to
  `aerocommand/{org_id}/command/{vehicle_id}/ack`.
- If `DRONE_IP` is set, the agent derives the stream URL as `http://<drone-ip>:5000/video`
  unless `CAMERA_STREAM_PUBLIC_URL` is set explicitly.
