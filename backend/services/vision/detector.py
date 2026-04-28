from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter

import numpy as np

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional at import time
    YOLO = None


@dataclass(slots=True)
class DetectionResult:
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(slots=True)
class VisionInference:
    detections: list[DetectionResult]
    inference_ms: float


class YoloDetector:
    def __init__(self, model_name: str, confidence: float, class_allowlist: set[str]) -> None:
        if YOLO is None:
            raise RuntimeError("ultralytics is not available. Install the backend vision dependencies.")
        self._model = YOLO(model_name)
        self._confidence = confidence
        self._class_allowlist = class_allowlist

    def infer(self, frame: np.ndarray) -> VisionInference:
        started = perf_counter()
        results = self._model.predict(source=frame, conf=self._confidence, verbose=False)
        detections: list[DetectionResult] = []
        if not results:
            return VisionInference(detections=detections, inference_ms=(perf_counter() - started) * 1000.0)

        result = results[0]
        names = result.names if hasattr(result, "names") else {}
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return VisionInference(detections=detections, inference_ms=(perf_counter() - started) * 1000.0)

        xyxy = boxes.xyxy.cpu().numpy().astype(int).tolist() if boxes.xyxy is not None else []
        confs = boxes.conf.cpu().numpy().tolist() if boxes.conf is not None else []
        classes = boxes.cls.cpu().numpy().astype(int).tolist() if boxes.cls is not None else []

        for idx, coords in enumerate(xyxy):
            if len(coords) != 4:
                continue
            class_id = classes[idx] if idx < len(classes) else -1
            label = str(names.get(class_id, class_id))
            if label not in self._class_allowlist:
                continue
            confidence = float(confs[idx]) if idx < len(confs) else 0.0
            x1, y1, x2, y2 = coords
            detections.append(DetectionResult(label=label, confidence=confidence, x1=x1, y1=y1, x2=x2, y2=y2))

        return VisionInference(detections=detections, inference_ms=(perf_counter() - started) * 1000.0)


@lru_cache(maxsize=1)
def get_detector(model_name: str, confidence: float, class_allowlist_csv: str) -> YoloDetector:
    class_allowlist = {part.strip() for part in class_allowlist_csv.split(",") if part.strip()}
    return YoloDetector(model_name=model_name, confidence=confidence, class_allowlist=class_allowlist)

