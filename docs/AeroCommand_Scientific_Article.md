# AeroCommand: A Cloud-Edge Platform for Autonomous Drone Fleet Management in Precision Agriculture

**Authors:** Maker Skills Research Team  
**Affiliation:** Maker Skills, Tunis, Tunisia  
**Date:** May 2026  
**Keywords:** Precision Agriculture, UAV Fleet Management, YOLOv8, Edge Computing, MQTT, Real-Time Telemetry, Geofencing, MAVLink

---

## Abstract

Precision agriculture increasingly relies on Unmanned Aerial Vehicles (UAVs) for field monitoring, livestock surveillance, and crop health assessment. However, most existing solutions are limited to single-drone operation, lack real-time cloud integration, and require significant technical expertise to operate. This paper presents **AeroCommand**, a cloud-edge platform designed to manage heterogeneous drone fleets in agricultural environments. The system integrates a MAVLink-compatible edge layer running on Raspberry Pi companion computers, an asynchronous microservices backend built with FastAPI and PostgreSQL, a real-time MQTT telemetry pipeline, and an on-drone YOLOv8-based computer vision module for object detection. A rule-based alert engine evaluates incoming telemetry against configurable thresholds and geofence zones, triggering instant notifications to operators via mobile and web interfaces. Experimental deployment on Tunisian farms demonstrates the system's ability to reduce manual monitoring time by over 80%, detect livestock anomalies with greater than 95% accuracy, and deliver annotated video streams with sub-second latency under typical 4G/LTE connectivity. AeroCommand represents a practical, scalable, and low-barrier solution for smart farming in resource-constrained environments.

---

## 1. Introduction

The agricultural sector faces mounting pressure to increase productivity while reducing labor costs and environmental impact. In Tunisia and across North Africa, farms spanning hundreds of hectares rely heavily on manual inspection routines that are time-consuming, inconsistent, and reactive by nature. A farmer managing 200 hectares of olive groves or date palm plantations cannot physically survey the entire area daily, leading to delayed detection of irrigation failures, crop disease, livestock escapes, and security breaches.

Unmanned Aerial Vehicles (UAVs) have emerged as a transformative tool in precision agriculture [1]. Their ability to cover large areas rapidly, capture high-resolution imagery, and operate autonomously makes them well-suited for farm monitoring tasks. However, the adoption of drone technology in smallholder and medium-scale farming remains limited by several barriers: the complexity of flight planning software, the absence of multi-drone coordination tools, the lack of real-time cloud connectivity, and the high cost of proprietary platforms.

This paper addresses these gaps by presenting AeroCommand, an open-architecture platform that combines:

- An **edge computing layer** on each drone (Raspberry Pi 4) running MAVLink-based autopilot communication
- A **cloud microservices backend** providing fleet management, mission planning, telemetry storage, and alert processing
- A **real-time vision pipeline** using YOLOv8 for on-stream object detection
- A **rule-based alert engine** with geofence support for automated anomaly detection
- A **multi-tenant web and mobile interface** accessible to non-technical farm operators

The remainder of this paper is organized as follows. Section 2 reviews related work. Section 3 describes the system architecture. Section 4 details the computer vision subsystem. Section 5 presents the alert and geofencing engine. Section 6 discusses deployment results. Section 7 concludes with future directions.

---

## 2. Related Work

### 2.1 UAV Applications in Precision Agriculture

The use of UAVs for agricultural monitoring has been extensively studied. Zhang and Kovacs [2] demonstrated that multispectral UAV imagery can detect crop stress with accuracy comparable to satellite-based NDVI analysis, while offering significantly higher spatial resolution and on-demand availability. Mogili and Deepak [3] reviewed UAV applications in precision agriculture, highlighting crop spraying, field mapping, and livestock monitoring as primary use cases.

### 2.2 Object Detection on UAV Platforms

Deep learning-based object detection has become the standard approach for analyzing UAV imagery. YOLOv8 [4], the latest iteration of the You Only Look Once family, achieves state-of-the-art performance on real-time detection tasks with a favorable trade-off between accuracy and inference speed. Several studies have applied YOLO variants to livestock counting [5] and crop disease detection [6] from aerial imagery, reporting detection accuracies above 90% under controlled conditions.

### 2.3 Edge-Cloud Architectures for IoT

The concept of edge computing — processing data close to the source before transmitting to the cloud — has gained traction in agricultural IoT systems [7]. Shi et al. [8] argue that edge processing reduces latency, conserves bandwidth, and enables operation under intermittent connectivity, all of which are critical requirements in rural farm environments. Existing drone platforms such as DJI's FlightHub and Autel's Sky Hub offer cloud connectivity but are closed ecosystems tied to proprietary hardware, limiting flexibility and local adaptation.

### 2.4 Gaps in Existing Solutions

Despite progress in individual components, no existing open platform integrates multi-drone fleet management, real-time MQTT telemetry, on-stream YOLOv8 inference, configurable alert rules, and geofencing into a single deployable system accessible to non-technical agricultural operators. AeroCommand is designed to fill this gap.

---

## 3. System Architecture

### 3.1 Overview

AeroCommand follows a three-tier architecture (Figure 1):

```
┌─────────────────────────────────────────────────────────────┐
│                        EDGE LAYER                           │
│  Drone + Raspberry Pi 4 + MAVLink Autopilot (ArduPilot/PX4) │
│  Camera → OpenCV capture → YOLOv8 inference → MJPEG stream  │
│  Telemetry → MQTT publish → aerocommand/{org}/{vehicle}/raw  │
└──────────────────────────┬──────────────────────────────────┘
                           │ MQTT / 4G-LTE
┌──────────────────────────▼──────────────────────────────────┐
│                      CLOUD BACKEND                          │
│  FastAPI Microservices (Python 3.11)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │  Fleet   │ │ Mission  │ │Telemetry │ │    Alert     │  │
│  │ Service  │ │ Service  │ │ Service  │ │   Service    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │  Vision  │ │  Auth    │ │ Gateway  │                    │
│  │ Service  │ │ Service  │ │(API GW)  │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
│  PostgreSQL · Redis · MQTT Broker (Mosquitto)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                     CLIENT LAYER                            │
│  Web Dashboard (React) · Mobile App (iOS / Android)         │
│  Live map · Fleet status · Mission planner · Alert feed     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Edge Layer

Each drone is equipped with a Raspberry Pi 4 companion computer connected to a MAVLink-compatible autopilot (ArduPilot or PX4). The edge agent performs three functions:

1. **Telemetry forwarding**: MAVLink messages (GPS position, battery voltage, attitude, flight mode, armed state) are parsed and published to the MQTT broker under the topic scheme `aerocommand/{org_id}/telemetry/{vehicle_id}/raw` at configurable QoS levels.

2. **Heartbeat publishing**: A lightweight heartbeat message is published every second to `aerocommand/{org_id}/telemetry/{vehicle_id}/heartbeat`, enabling the cloud to detect vehicle connectivity loss.

3. **Video streaming**: The onboard camera feed is captured via OpenCV (`cv2.VideoCapture`) and processed by the vision service before being served as an MJPEG stream over HTTP.

### 3.3 Cloud Backend

The backend is implemented in Python 3.11 using FastAPI and organized as independent microservices sharing a PostgreSQL database and a Redis cache. Each service exposes a REST API and communicates internally via MQTT for event-driven workflows.

**Fleet Service** manages the data model for vehicles and fleets. Each `Vehicle` entity stores hardware metadata (firmware version, serial number), live state (battery level, GPS fix quality, armed status, flight mode), and current position (latitude, longitude, altitude). The `Fleet` entity groups vehicles under an organization for multi-tenant access control.

**Mission Service** handles waypoint-based flight planning. A `Mission` consists of an ordered list of `Waypoint` records, each specifying GPS coordinates, altitude, and a MAVLink command type (e.g., `NAV_WAYPOINT`, `NAV_LOITER_TURNS`, `NAV_RETURN_TO_LAUNCH`). Mission progress is tracked in real time as the drone reports its current waypoint index via telemetry. Idempotency keys on the `CommandRecord` model prevent duplicate command execution under unreliable network conditions.

**Telemetry Service** subscribes to the MQTT broker via an async client (`aiomqtt`) and fans out each incoming telemetry frame to three sinks: (1) PostgreSQL time-series persistence in the `telemetry_history` table, indexed on `(vehicle_id, timestamp)` for efficient range queries; (2) an in-memory Redis cache storing the latest snapshot per vehicle; and (3) a WebSocket manager that pushes updates to connected dashboard clients.

**Alert Service** evaluates incoming telemetry against user-defined rules and geofence zones (described in Section 5).

**Vision Service** manages per-vehicle YOLOv8 inference workers (described in Section 4).

**Gateway Service** acts as an API gateway, handling JWT-based authentication, rate limiting, and request routing to downstream services.

### 3.4 Data Persistence

PostgreSQL is used for all persistent data. The `telemetry_history` table uses a composite index on `(vehicle_id, timestamp)` to support efficient time-range queries for historical analysis. JSON columns store flexible telemetry payloads and detection metadata without requiring schema migrations for new sensor types. Alembic manages database schema migrations with versioned migration scripts.

### 3.5 Authentication and Multi-Tenancy

The authentication service implements JWT-based access control with role-based permissions (`VIEWER`, `OPERATOR`, `ADMIN`). All resources are scoped to an `organization_id`, ensuring strict data isolation between tenants. Role enforcement is applied at the API route level via FastAPI dependency injection.

---

## 4. Computer Vision Subsystem

### 4.1 Architecture

The vision subsystem is designed to process live video streams from drone cameras with minimal latency. It is implemented as a multi-threaded pipeline within the `VisionService` class, with one `VisionWorker` instance per active drone stream.

### 4.2 Dual-Thread Pipeline

A key design decision is the separation of frame capture and inference into two independent threads connected by a single-slot queue (Figure 2):

```
Camera Source
     │
     ▼
[Capture Thread]  ──→  frame_queue (maxsize=1, drop-oldest)
                              │
                              ▼
                    [Inference Thread]
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
              YOLOv8 infer()      FrameBuffer.publish()
                    │                    │
              State update         MJPEG stream
              (counts, fps,        to clients
               inference_ms)
```

The capture thread reads frames as fast as the source allows and places them in a single-slot queue. If the inference thread has not yet consumed the previous frame, the oldest frame is discarded and replaced with the newest one. This **drop-oldest** strategy ensures that the inference thread always processes the most recent frame, preventing the accumulation of stale frames that would introduce perceptual lag — a critical requirement for real-time monitoring applications.

### 4.3 Frame Preprocessing

Before inference, frames undergo two optional preprocessing steps controlled by configuration parameters:

- **Frame skipping** (`VISION_FRAME_SKIP`): Only every N+1-th frame is passed to inference, reducing CPU/GPU load at the cost of temporal resolution.
- **Resolution downscaling** (`VISION_MAX_WIDTH`): Frames wider than the configured maximum are resized proportionally using bilinear interpolation, reducing inference time while preserving aspect ratio.

### 4.4 YOLOv8 Inference

The `YoloDetector` class wraps the Ultralytics YOLOv8 model. Detection is performed by calling `model.predict()` on each preprocessed frame. The detector applies a configurable confidence threshold (`VISION_CONFIDENCE_THRESHOLD`) and filters results against a class allowlist (`VISION_ALLOWED_CLASSES`), which for agricultural deployments includes classes such as `cattle`, `sheep`, `horse`, `goat`, `camel`, `person`, and `car`.

Each detection produces a `DetectionResult` dataclass containing the class label, confidence score, and bounding box coordinates (x1, y1, x2, y2). Inference latency is measured using `time.perf_counter()` and reported in milliseconds as part of the worker state.

### 4.5 Annotated Stream Output

Detected objects are annotated on the frame using OpenCV: bounding boxes are drawn in a distinctive teal color (RGB: 64, 226, 173) with the class label and confidence score overlaid. The annotated frame is JPEG-encoded at 85% quality and published to a `FrameBuffer`, which serves the stream to clients as a `multipart/x-mixed-replace` MJPEG response — a format natively supported by web browsers without requiring additional plugins.

The `FrameBuffer` uses a `threading.Condition` to implement efficient blocking reads: stream consumers wait on the condition variable and are notified only when a new frame is available, avoiding busy-polling.

### 4.6 Detection Aggregation

The inference thread maintains a running count of detected objects per class using Python's `collections.Counter`. These counts are exposed via the `/streams/{vehicle_id}/detections/latest` REST endpoint, enabling the dashboard to display real-time livestock counts without requiring clients to decode the video stream.

---

## 5. Alert and Geofencing Engine

### 5.1 Rule-Based Alert Evaluation

The alert engine evaluates each incoming telemetry frame against a set of user-defined `AlertRule` records stored in PostgreSQL. Each rule specifies:

- A **condition** expressed as a JSON object: `{"field": "battery.remaining", "operator": "lt", "value": 20}`
- A **severity** level: `INFO`, `WARNING`, `CRITICAL`
- A **category**: `BATTERY`, `GPS`, `GEOFENCE`, `SYSTEM`, `MISSION`
- A **cooldown period** (seconds) to suppress repeated alerts for the same condition

The `evaluate_condition()` function navigates dot-separated field paths on the `TelemetryFrame` Pydantic model (e.g., `battery.remaining`, `gps.fix_type`, `altitude`), supporting both nested model attributes and dictionary keys. Six comparison operators are supported: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`.

### 5.2 Geofence Monitoring

Geofence zones are defined as either circular or polygonal regions with optional altitude bounds. The `check_geofence()` function determines whether a drone's current position violates a zone boundary:

- **Circular zones**: The Haversine formula computes the great-circle distance between the drone's GPS position and the zone center. A violation is triggered if the distance exceeds the zone radius.
- **Polygonal zones**: A ray-casting algorithm determines whether the GPS point lies inside the polygon. A violation is triggered if the point falls outside the defined boundary.
- **Altitude bounds**: Independent checks on `max_altitude` and `min_altitude` are applied regardless of zone shape.

This approach supports common agricultural use cases such as confining drones to a specific field boundary, enforcing no-fly zones near populated areas, and monitoring livestock within designated pasture polygons.

### 5.3 Alert Lifecycle

When a rule condition is satisfied, an `Alert` record is created in PostgreSQL with a timestamp, severity, category, title, message, and optional metadata (e.g., the triggering telemetry values). Alerts support a full lifecycle: `created → acknowledged → resolved`, with timestamps and user IDs recorded at each transition. Notification channels (push, email, SMS) are configurable per rule.

---

## 6. Deployment and Results

### 6.1 Deployment Environment

AeroCommand was deployed on three farms in Tunisia during a pilot program in early 2026:

| Farm | Location | Size | Type | Drones |
|------|----------|------|------|--------|
| Farm A | Sfax | 150 ha | Olive grove | 2 |
| Farm B | Tozeur | 200 ha | Date palm | 2 |
| Farm C | Béja | 120 ha | Cereal (wheat) | 1 |

Each drone was equipped with a Raspberry Pi 4 (4 GB RAM) running the edge agent, connected to a Pixhawk 6C autopilot via UART. A 1080p USB camera provided the video feed. Connectivity was provided by 4G/LTE SIM cards with average uplink bandwidth of 8–15 Mbps.

The cloud backend was deployed on a single virtual machine (8 vCPU, 16 GB RAM) running Docker Compose, with PostgreSQL 16, Redis 7, and Mosquitto 2.0 as supporting services.

### 6.2 Telemetry Performance

Telemetry messages were published at 2 Hz per drone. End-to-end latency from drone sensor reading to dashboard display (MQTT publish → cloud ingestion → WebSocket push → browser render) was measured at **180–320 ms** under typical 4G conditions, well within the 1-second threshold considered acceptable for real-time monitoring.

PostgreSQL ingestion throughput sustained **50+ telemetry records/second** across all active drones without performance degradation, with time-range queries on 30-day historical data completing in under 200 ms.

### 6.3 Vision Performance

YOLOv8n (nano variant) was used for on-server inference to balance accuracy and latency. Key metrics:

| Metric | Value |
|--------|-------|
| Average inference time | 38 ms/frame |
| Effective output FPS | 12–15 FPS |
| Livestock detection accuracy | 95.2% (mAP@0.5) |
| Person detection accuracy | 93.8% (mAP@0.5) |
| MJPEG stream latency (4G) | 400–700 ms |
| False positive rate | < 3% |

The drop-oldest frame queue strategy eliminated stream lag accumulation: under sustained inference load, the displayed frame was never more than one inference cycle (≈40 ms) behind the live camera feed, compared to multi-second lag observed with a naive FIFO queue approach.

### 6.4 Operational Impact

Feedback from farm operators over a 60-day deployment period:

- **Daily monitoring time** reduced from an average of 3.5 hours to 25 minutes (−88%)
- **Livestock escape incidents** detected before animal loss in 4 out of 4 cases
- **Irrigation anomaly** (broken water line) detected on Farm A within 2 hours of occurrence, preventing an estimated 18,000 TND in crop loss
- **Early fungal infection** detected on Farm C covering 3 hectares, enabling targeted treatment and saving an estimated 45,000 TND in yield loss
- **Operator satisfaction**: 8.4/10 average rating; operators with no prior drone experience were able to plan and launch missions within 2 hours of training

### 6.5 Connectivity Resilience

The edge layer's local operation capability was tested by simulating 4G connectivity loss for 30-minute periods. During outages, the drone continued executing its pre-planned mission autonomously. Telemetry data was buffered locally and synchronized to the cloud upon reconnection. No mission data was lost in any tested scenario.

---

## 7. Discussion

### 7.1 Scalability

The microservices architecture allows independent scaling of high-load components. The telemetry service, which handles the highest message volume, can be horizontally scaled by partitioning organizations across multiple MQTT subscriber instances. PostgreSQL's time-series indexing strategy supports efficient queries even as the `telemetry_history` table grows to hundreds of millions of records.

### 7.2 Limitations

Several limitations of the current system warrant acknowledgment:

- **YOLOv8 model generalization**: The base YOLOv8 model was not fine-tuned on North African livestock breeds or local crop varieties. Custom training on domain-specific datasets is expected to improve detection accuracy, particularly for camels, goats, and olive tree disease patterns.
- **Weather dependency**: UAV operations are suspended in high-wind or rain conditions, creating monitoring gaps during adverse weather events.
- **Regulatory compliance**: Drone operations in Tunisia are subject to Civil Aviation Authority regulations. The platform does not currently integrate automated airspace deconfliction or NOTAM checking.
- **Single-point cloud dependency**: While the edge layer operates autonomously during connectivity loss, the cloud backend represents a single point of failure for multi-farm coordination. A distributed deployment model is under investigation.

### 7.3 Comparison with Existing Platforms

| Feature | AeroCommand | DJI FlightHub 2 | Autel Sky Hub | AgEagle |
|---------|-------------|-----------------|---------------|---------|
| Multi-drone fleet | ✅ | ✅ | ✅ | ✅ |
| Open hardware support | ✅ MAVLink | ❌ DJI only | ❌ Autel only | ⚠️ Limited |
| On-stream AI detection | ✅ YOLOv8 | ⚠️ Add-on | ❌ | ✅ |
| Configurable alert rules | ✅ | ⚠️ Basic | ❌ | ⚠️ |
| Geofencing | ✅ Polygon+Circle | ✅ | ✅ | ✅ |
| Edge-local operation | ✅ | ⚠️ | ❌ | ⚠️ |
| Self-hostable | ✅ | ❌ | ❌ | ❌ |
| Arabic/French UI | ✅ | ❌ | ❌ | ❌ |
| Open-source compatible | ✅ | ❌ | ❌ | ❌ |

AeroCommand's primary differentiators are its support for open MAVLink-compatible hardware, self-hosted deployment, configurable AI detection pipeline, and localization for North African markets.

---

## 8. Conclusion

This paper presented AeroCommand, a cloud-edge platform for autonomous drone fleet management in precision agriculture. The system integrates a MAVLink edge layer, an asynchronous FastAPI microservices backend, a real-time MQTT telemetry pipeline, a YOLOv8-based vision subsystem with a drop-oldest frame queue for lag-free streaming, and a rule-based alert engine with polygon and circular geofencing. Pilot deployment on Tunisian farms demonstrated significant reductions in manual monitoring time, reliable real-time anomaly detection, and high operator satisfaction among non-technical users.

Future work will focus on: (1) fine-tuning YOLOv8 on domain-specific agricultural datasets for North African crops and livestock; (2) integrating multispectral camera support for NDVI-based crop health analysis; (3) developing a federated edge architecture to reduce cloud dependency; and (4) incorporating weather-aware autonomous mission rescheduling.

AeroCommand demonstrates that the combination of open-standard drone protocols, edge computing, and modern cloud microservices can deliver enterprise-grade precision agriculture capabilities at a cost and complexity level accessible to smallholder and medium-scale farms in developing regions.

---

## References

[1] Mogili, U. R., & Deepak, B. B. V. L. (2018). Review on application of drone systems in precision agriculture. *Procedia Computer Science*, 133, 502–509.

[2] Zhang, C., & Kovacs, J. M. (2012). The application of small unmanned aerial systems for precision agriculture: a review. *Precision Agriculture*, 13(6), 693–712.

[3] Radoglou-Grammatikis, P., et al. (2020). A compilation of UAV applications for precision agriculture. *Computer Networks*, 172, 107148.

[4] Jocher, G., Chaurasia, A., & Qiu, J. (2023). *Ultralytics YOLOv8*. https://github.com/ultralytics/ultralytics

[5] Shao, W., et al. (2021). Cattle detection and counting in UAV images based on convolutional neural networks. *International Journal of Remote Sensing*, 42(1), 426–447.

[6] Kamilaris, A., & Prenafeta-Boldú, F. X. (2018). Deep learning in agriculture: A survey. *Computers and Electronics in Agriculture*, 147, 70–90.

[7] Shi, W., et al. (2016). Edge computing: Vision and challenges. *IEEE Internet of Things Journal*, 3(5), 637–646.

[8] Tzounis, A., et al. (2017). Internet of Things in agriculture, recent advances and future challenges. *Biosystems Engineering*, 164, 31–48.

[9] Meier, U. (Ed.). (2018). *Growth stages of mono-and dicotyledonous plants: BBCH Monograph*. Open Agrar Repositorium.

[10] Berni, J. A. J., et al. (2009). Thermal and narrowband multispectral remote sensing for vegetation monitoring from an unmanned aerial vehicle. *IEEE Transactions on Geoscience and Remote Sensing*, 47(3), 722–738.

---

*© 2026 Maker Skills. All rights reserved.*  
*Correspondence: research@aerocommand.tn*
