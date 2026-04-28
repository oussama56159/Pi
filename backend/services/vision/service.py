from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any

from backend.shared.config import get_base_settings

from .detector import DetectionResult, get_detector
from .streaming import FrameBuffer, RateLimiter

logger = logging.getLogger(__name__)

_CV2_IMPORT_ERROR: str | None = None


def _get_cv2():
    global _CV2_IMPORT_ERROR
    try:
        import cv2  # type: ignore
        return cv2
    except Exception as exc:
        _CV2_IMPORT_ERROR = str(exc)
        raise


def get_vision_import_error() -> str | None:
    """If vision dependencies failed to import, returns the import error message."""
    return _CV2_IMPORT_ERROR


@dataclass(slots=True)
class VisionWorkerState:
    vehicle_id: str
    source_url: str
    running: bool = False
    started_at: str | None = None
    updated_at: str | None = None
    fps: float = 0.0
    inference_ms: float = 0.0
    error: str | None = None
    detections: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


class VisionWorker:
    def __init__(self, vehicle_id: str, source_url: str) -> None:
        self.vehicle_id = vehicle_id
        self.source_url = source_url
        self.buffer = FrameBuffer()
        self.state = VisionWorkerState(vehicle_id=vehicle_id, source_url=source_url)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"vision-{self.vehicle_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        try:
            cv2 = _get_cv2()
        except Exception as exc:
            self.state.error = f"Vision dependency import failed: {exc}"
            self.state.running = False
            logger.error("vision worker cannot start (cv2 import failed) vehicle=%s err=%s", self.vehicle_id, exc)
            return

        settings = get_base_settings()
        detector = get_detector(
            settings.VISION_MODEL_NAME,
            settings.VISION_CONFIDENCE_THRESHOLD,
            settings.VISION_ALLOWED_CLASSES,
        )
        fps_limiter = RateLimiter(settings.VISION_OUTPUT_FPS)
        capture = cv2.VideoCapture(self.source_url)
        if not capture.isOpened():
            self.state.error = f"Cannot open stream: {self.source_url}"
            self.state.running = False
            logger.warning("vision worker failed to open stream vehicle=%s source=%s", self.vehicle_id, self.source_url)
            return

        self.state.running = True
        self.state.started_at = datetime.now(tz=timezone.utc).isoformat()
        frame_counter = 0
        last_frame_time = time.time()

        try:
            while not self._stop_event.is_set():
                ok, frame = capture.read()
                if not ok or frame is None:
                    self.state.error = "Stream frame read failed"
                    time.sleep(0.1)
                    continue

                frame_counter += 1
                if settings.VISION_FRAME_SKIP > 0 and frame_counter % (settings.VISION_FRAME_SKIP + 1) != 0:
                    continue

                if settings.VISION_MAX_WIDTH > 0 and frame.shape[1] > settings.VISION_MAX_WIDTH:
                    ratio = settings.VISION_MAX_WIDTH / float(frame.shape[1])
                    frame = cv2.resize(frame, (settings.VISION_MAX_WIDTH, int(frame.shape[0] * ratio)))

                inference = detector.infer(frame)
                annotated = _draw_detections(frame, inference.detections)
                ok_jpeg, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ok_jpeg and encoded is not None:
                    self.buffer.publish(encoded.tobytes())

                counts = Counter(det.label for det in inference.detections)
                self.state.detections = [asdict(det) for det in inference.detections]
                self.state.counts = dict(counts)
                self.state.inference_ms = inference.inference_ms
                now = time.time()
                dt = max(0.001, now - last_frame_time)
                self.state.fps = 1.0 / dt
                last_frame_time = now
                self.state.updated_at = datetime.now(tz=timezone.utc).isoformat()
                self.state.error = None

                fps_limiter.wait()
        except Exception as exc:
            self.state.error = str(exc)
            logger.exception("vision worker crashed vehicle=%s", self.vehicle_id)
        finally:
            capture.release()
            self.state.running = False


def _draw_detections(frame, detections: list[DetectionResult]):
    cv2 = _get_cv2()
    for det in detections:
        cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), (64, 226, 173), 2)
        label = f"{det.label} {det.confidence:.2f}"
        cv2.putText(frame, label, (det.x1, max(20, det.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (64, 226, 173), 2)
    return frame


class VisionService:
    def __init__(self) -> None:
        self._workers: dict[str, VisionWorker] = {}
        self._lock = threading.Lock()

    def start_stream(self, vehicle_id: str, source_url: str) -> VisionWorkerState:
        with self._lock:
            current = self._workers.get(vehicle_id)
            if current is not None:
                current.stop()
            worker = VisionWorker(vehicle_id=vehicle_id, source_url=source_url)
            self._workers[vehicle_id] = worker
            worker.start()
            return worker.state

    def stop_stream(self, vehicle_id: str) -> bool:
        with self._lock:
            worker = self._workers.pop(vehicle_id, None)
            if worker is None:
                return False
            worker.stop()
            return True

    def get_state(self, vehicle_id: str) -> VisionWorkerState | None:
        worker = self._workers.get(vehicle_id)
        if worker is None:
            return None
        return worker.state

    def get_stream_buffer(self, vehicle_id: str) -> FrameBuffer | None:
        worker = self._workers.get(vehicle_id)
        if worker is None:
            return None
        return worker.buffer


_vision_service = VisionService()


def get_vision_service() -> VisionService:
    return _vision_service

