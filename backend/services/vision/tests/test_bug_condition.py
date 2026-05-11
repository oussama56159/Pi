"""
Bug Condition Exploration Test — YOLO Stream Lag

**Validates: Requirements 1.1, 1.2, 1.3**

This test surfaces counterexamples that demonstrate the capture loop is blocked by
`detector.infer()` in the UNFIXED `VisionWorker._run()`.

EXPECTED OUTCOME on UNFIXED code: ALL assertions FAIL.
  - `capture.read()` is blocked for the full inference duration (~200 ms per frame)
  - `FrameBuffer` receives far fewer than 5 frames in 2 seconds
  - Effective output FPS is far below `VISION_OUTPUT_FPS` (8.0 fps)

When the fix is applied (Task 3), this same test should PASS, confirming the bug is fixed.

Bug Condition:
    isBugCondition(X) = X.yolo_enabled = true AND X.stream_running = true
"""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from backend.services.vision.detector import VisionInference
from backend.services.vision.service import VisionWorker
from backend.services.vision.streaming import FrameBuffer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(height: int = 480, width: int = 640) -> np.ndarray:
    """Return a synthetic BGR frame filled with zeros."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _make_mock_capture(frame: np.ndarray, stop_event: threading.Event) -> MagicMock:
    """
    Return a mock cv2.VideoCapture that:
    - isOpened() → True
    - read() → (True, frame) immediately (no blocking), until stop_event is set
    - release() → no-op
    """
    cap = MagicMock()
    cap.isOpened.return_value = True

    def _read():
        if stop_event.is_set():
            return False, None
        return True, frame.copy()

    cap.read.side_effect = _read
    return cap


def _make_mock_detector(inference_duration_s: float) -> MagicMock:
    """
    Return a mock detector whose infer() sleeps for `inference_duration_s` seconds,
    simulating slow CPU inference.
    """
    detector = MagicMock()

    def _infer(frame):
        time.sleep(inference_duration_s)
        return VisionInference(detections=[], inference_ms=inference_duration_s * 1000.0)

    detector.infer.side_effect = _infer
    return detector


def _run_worker_and_measure(
    inference_duration_s: float,
    run_duration_s: float,
    frame_height: int = 480,
    frame_width: int = 640,
) -> dict[str, Any]:
    """
    Run VisionWorker for `run_duration_s` seconds with mocked capture and detector.

    Returns a dict with:
      - read_intervals: list of wall-clock intervals between consecutive capture.read() calls
      - frames_published: number of frames published to FrameBuffer
      - elapsed_s: actual elapsed time
    """
    frame = _make_frame(frame_height, frame_width)
    stop_event = threading.Event()
    mock_cap = _make_mock_capture(frame, stop_event)

    read_timestamps: list[float] = []

    original_read = mock_cap.read.side_effect

    def _instrumented_read():
        read_timestamps.append(time.monotonic())
        return original_read()

    mock_cap.read.side_effect = _instrumented_read

    mock_detector = _make_mock_detector(inference_duration_s)

    # Count frames published to FrameBuffer
    frames_published: list[float] = []
    original_publish = FrameBuffer.publish

    def _counting_publish(self, jpeg_bytes: bytes) -> None:
        frames_published.append(time.monotonic())
        original_publish(self, jpeg_bytes)

    worker = VisionWorker(vehicle_id="test-drone", source_url="mock://stream")

    # Patch cv2 and detector
    mock_cv2 = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_cap
    mock_cv2.resize.side_effect = lambda frame, size: frame
    mock_cv2.imencode.return_value = (True, np.array([0xFF, 0xD8, 0xFF], dtype=np.uint8))

    with (
        patch("backend.services.vision.service._get_cv2", return_value=mock_cv2),
        patch("backend.services.vision.service.get_detector", return_value=mock_detector),
        patch.object(FrameBuffer, "publish", _counting_publish),
        patch(
            "backend.shared.config.get_base_settings",
            return_value=_make_settings(
                vision_output_fps=8.0,
                vision_frame_skip=0,
                vision_max_width=0,
            ),
        ),
    ):
        worker.start()
        time.sleep(run_duration_s)
        stop_event.set()
        worker.stop()
        # Give the thread a moment to exit
        if worker._thread:
            worker._thread.join(timeout=2.0)

    # Compute inter-read intervals
    read_intervals: list[float] = []
    for i in range(1, len(read_timestamps)):
        read_intervals.append(read_timestamps[i] - read_timestamps[i - 1])

    return {
        "read_intervals": read_intervals,
        "frames_published": len(frames_published),
        "frame_publish_timestamps": frames_published,
        "elapsed_s": run_duration_s,
    }


class _FakeSettings:
    """Minimal settings object for testing."""

    def __init__(
        self,
        vision_output_fps: float = 8.0,
        vision_frame_skip: int = 0,
        vision_max_width: int = 0,
        vision_model_name: str = "yolov8n.pt",
        vision_confidence_threshold: float = 0.35,
        vision_allowed_classes: str = "person,dog",
    ):
        self.VISION_OUTPUT_FPS = vision_output_fps
        self.VISION_FRAME_SKIP = vision_frame_skip
        self.VISION_MAX_WIDTH = vision_max_width
        self.VISION_MODEL_NAME = vision_model_name
        self.VISION_CONFIDENCE_THRESHOLD = vision_confidence_threshold
        self.VISION_ALLOWED_CLASSES = vision_allowed_classes


def _make_settings(**kwargs) -> _FakeSettings:
    return _FakeSettings(**kwargs)


# ---------------------------------------------------------------------------
# Property-Based Test: Capture Loop Blocked by Inference
#
# Validates: Requirements 1.1, 1.2, 1.3
#
# For any inference duration in [50, 300] ms and any valid frame size,
# the UNFIXED code should block capture.read() for the full inference duration.
# This test ASSERTS the CORRECT (fixed) behavior — it will FAIL on unfixed code.
# ---------------------------------------------------------------------------

@given(
    inference_ms=st.integers(min_value=50, max_value=300),
    frame_height=st.integers(min_value=240, max_value=720),
    frame_width=st.integers(min_value=320, max_value=1280),
)
@settings(
    max_examples=3,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
def test_capture_not_blocked_by_inference(
    inference_ms: int,
    frame_height: int,
    frame_width: int,
) -> None:
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    Property: For any inference duration, the inter-read interval between consecutive
    capture.read() calls MUST be less than the inference duration.

    On UNFIXED code: FAILS — capture.read() is blocked for the full inference duration.
    On FIXED code: PASSES — capture runs independently of inference.
    """
    inference_duration_s = inference_ms / 1000.0
    run_duration_s = max(1.5, inference_duration_s * 6)

    result = _run_worker_and_measure(
        inference_duration_s=inference_duration_s,
        run_duration_s=run_duration_s,
        frame_height=frame_height,
        frame_width=frame_width,
    )

    read_intervals = result["read_intervals"]
    assert len(read_intervals) >= 2, (
        f"Too few capture.read() calls recorded ({len(read_intervals)}); "
        "worker may not have started correctly."
    )

    # On FIXED code: inter-read intervals should be much shorter than inference duration
    # (capture runs freely, not blocked by inference).
    # On UNFIXED code: inter-read intervals ≈ inference_duration_s (capture is blocked).
    max_interval = max(read_intervals)
    mean_interval = sum(read_intervals) / len(read_intervals)

    assert mean_interval < inference_duration_s, (
        f"COUNTEREXAMPLE FOUND: capture.read() is BLOCKED by inference.\n"
        f"  inference_duration_s = {inference_duration_s:.3f} s ({inference_ms} ms)\n"
        f"  mean inter-read interval = {mean_interval * 1000:.1f} ms\n"
        f"  max inter-read interval  = {max_interval * 1000:.1f} ms\n"
        f"  frame size = {frame_height}x{frame_width}\n"
        f"  This confirms Bug Condition: capture.read() is blocked by detector.infer().\n"
        f"  Requirements 1.1, 1.2 violated."
    )


# ---------------------------------------------------------------------------
# Concrete Test: FrameBuffer receives ≥5 frames in 2 seconds with 200 ms inference
#
# Validates: Requirements 1.2, 1.3
#
# With 200 ms inference and VISION_OUTPUT_FPS=8 (125 ms interval), the FIXED code
# should publish ≥5 frames in 2 seconds. The UNFIXED code publishes ~2 frames
# (blocked for 200 ms per frame + 125 ms limiter = ~325 ms per frame → ~6 frames/2s,
# but the fps_limiter is placed AFTER inference so effective rate is 1/0.325 ≈ 3 fps).
# ---------------------------------------------------------------------------

def test_framebuffer_receives_enough_frames_with_slow_inference() -> None:
    """
    **Validates: Requirements 1.2, 1.3**

    With 200 ms inference and VISION_OUTPUT_FPS=8.0, the worker MUST publish
    at least 5 frames to FrameBuffer within 2 seconds.

    On UNFIXED code: FAILS — only ~2-4 frames published (capture blocked by inference).
    On FIXED code: PASSES — capture runs freely, ≥5 frames published.
    """
    result = _run_worker_and_measure(
        inference_duration_s=0.200,
        run_duration_s=2.0,
    )

    frames_published = result["frames_published"]
    assert frames_published >= 5, (
        f"COUNTEREXAMPLE FOUND: FrameBuffer received only {frames_published} frames in 2 seconds.\n"
        f"  Expected: ≥5 frames (VISION_OUTPUT_FPS=8.0, inference=200ms)\n"
        f"  Actual:   {frames_published} frames\n"
        f"  This confirms the stream buffer falls behind the live feed.\n"
        f"  Requirements 1.2, 1.3 violated."
    )


# ---------------------------------------------------------------------------
# Concrete Test: Effective output FPS within 20% of VISION_OUTPUT_FPS
#
# Validates: Requirements 1.3
#
# With VISION_OUTPUT_FPS=8.0, the effective FPS should be 6.4–9.6 fps.
# On UNFIXED code: effective FPS ≈ 1/(inference_ms + limiter_sleep_ms) << 8.0 fps.
# ---------------------------------------------------------------------------

def test_effective_fps_within_20_percent_of_target() -> None:
    """
    **Validates: Requirements 1.3**

    The effective output FPS (frames published per second) MUST be within 20% of
    VISION_OUTPUT_FPS (8.0 fps), i.e., between 6.4 and 9.6 fps.

    On UNFIXED code: FAILS — fps_limiter.wait() is placed after inference, so
    effective FPS = 1 / (inference_ms + limiter_sleep_ms) << 8.0 fps.
    On FIXED code: PASSES — fps_limiter gates capture rate independently.
    """
    target_fps = 8.0
    run_duration_s = 3.0
    inference_duration_s = 0.150  # 150 ms inference

    result = _run_worker_and_measure(
        inference_duration_s=inference_duration_s,
        run_duration_s=run_duration_s,
    )

    frames_published = result["frames_published"]
    timestamps = result["frame_publish_timestamps"]

    if len(timestamps) >= 2:
        # Compute effective FPS from actual publish timestamps
        actual_duration = timestamps[-1] - timestamps[0]
        if actual_duration > 0:
            effective_fps = (len(timestamps) - 1) / actual_duration
        else:
            effective_fps = 0.0
    else:
        effective_fps = 0.0

    lower_bound = target_fps * 0.80  # 6.4 fps
    upper_bound = target_fps * 1.20  # 9.6 fps

    assert lower_bound <= effective_fps <= upper_bound, (
        f"COUNTEREXAMPLE FOUND: Effective output FPS is outside ±20% of target.\n"
        f"  target_fps       = {target_fps:.1f} fps\n"
        f"  effective_fps    = {effective_fps:.2f} fps\n"
        f"  acceptable range = [{lower_bound:.1f}, {upper_bound:.1f}] fps\n"
        f"  frames_published = {frames_published} in {run_duration_s:.1f} s\n"
        f"  inference_ms     = {inference_duration_s * 1000:.0f} ms\n"
        f"  This confirms fps_limiter.wait() adds delay on top of inference time.\n"
        f"  Requirement 1.3 violated."
    )
