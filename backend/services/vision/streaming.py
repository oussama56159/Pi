from __future__ import annotations

from collections.abc import Generator
import threading
import time


class FrameBuffer:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest_jpeg: bytes | None = None
        self._version = 0

    def publish(self, jpeg_bytes: bytes) -> None:
        with self._condition:
            self._latest_jpeg = jpeg_bytes
            self._version += 1
            self._condition.notify_all()

    def stream(self, boundary: str = "frame") -> Generator[bytes, None, None]:
        last_version = -1
        while True:
            with self._condition:
                while self._version == last_version:
                    self._condition.wait(timeout=2.0)
                    if self._version == last_version and self._latest_jpeg is None:
                        # no frame yet, emit a heartbeat-style pause
                        break

                if self._latest_jpeg is None:
                    continue

                jpeg = self._latest_jpeg
                last_version = self._version

            yield (
                f"--{boundary}\r\n"
                "Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n\r\n"
            ).encode("utf-8")
            yield jpeg
            yield b"\r\n"

    def snapshot(self) -> bytes | None:
        with self._condition:
            return self._latest_jpeg


class RateLimiter:
    def __init__(self, fps: float) -> None:
        self._interval_s = 0.0 if fps <= 0 else (1.0 / fps)
        self._last_ts = 0.0

    def wait(self) -> None:
        if self._interval_s <= 0:
            return
        now = time.time()
        remaining = self._interval_s - (now - self._last_ts)
        if remaining > 0:
            time.sleep(remaining)
        self._last_ts = time.time()

