from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency in lightweight environments
    cv2 = None

logger = logging.getLogger(__name__)

_MJPEG_BOUNDARY = "frame"


@dataclass(frozen=True)
class CameraStreamConfig:
    enabled: bool
    host: str
    port: int
    path: str
    camera_index: int
    camera_url: str | None
    frame_width: int
    frame_height: int
    fps: float
    jpeg_quality: int
    token: str | None = None


class _FrameBuffer:
    def __init__(self, config: CameraStreamConfig):
        self._cfg = config
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = False
        self._latest_jpeg: bytes | None = None
        self._capture = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if cv2 is None:
            logger.warning("OpenCV is not available; camera stream server is disabled")
            return False

        source = self._cfg.camera_url
        if source:
            cap = cv2.VideoCapture(str(source))
        else:
            # On Linux (including WSL2), OpenCV's attempt to open a missing V4L2 device
            # can emit noisy backend errors. Short-circuit if the device node is absent.
            if sys.platform.startswith("linux"):
                dev = f"/dev/video{int(self._cfg.camera_index)}"
                if not os.path.exists(dev):
                    logger.warning(
                        "No camera device found at %s; camera stream server is disabled (set CAMERA_STREAM_ENABLED=false to disable explicitly)",
                        dev,
                    )
                    return False
            cap = cv2.VideoCapture(int(self._cfg.camera_index))

        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            logger.warning("Camera stream could not open capture (index=%s url=%s)", self._cfg.camera_index, source)
            return False

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._cfg.frame_width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._cfg.frame_height))
        except Exception:
            pass

        self._capture = cap
        self._thread = threading.Thread(target=self._run, name="aerocommand-mjpeg", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()

        cap = self._capture
        self._capture = None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    def get_latest(self, *, timeout_s: float = 2.0) -> bytes | None:
        deadline = time.time() + max(0.0, float(timeout_s))
        with self._cond:
            while self._latest_jpeg is None and not self._stop:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=remaining)
            return self._latest_jpeg

    def _run(self) -> None:
        fps = float(self._cfg.fps)
        interval_s = 0.0 if fps <= 0 else (1.0 / fps)

        quality = int(self._cfg.jpeg_quality)
        if quality < 10:
            quality = 10
        if quality > 95:
            quality = 95

        cap = self._capture
        if cap is None:
            return

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality] if cv2 is not None else []

        while True:
            with self._cond:
                if self._stop:
                    return

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            try:
                ok, encoded = cv2.imencode(".jpg", frame, encode_params)
            except Exception:
                ok, encoded = False, None

            if ok and encoded is not None:
                jpeg = encoded.tobytes()
                with self._cond:
                    self._latest_jpeg = jpeg
                    self._cond.notify_all()

            if interval_s > 0:
                time.sleep(interval_s)


class _MjpegServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        *,
        buffer: _FrameBuffer,
        stream_path: str,
        token: str | None,
    ):
        super().__init__(server_address, RequestHandlerClass)
        self.buffer = buffer
        self.stream_path = stream_path
        self.token = token


class _MjpegHandler(BaseHTTPRequestHandler):
    server: _MjpegServer  # type: ignore[assignment]

    def log_message(self, fmt: str, *args) -> None:  # pragma: no cover
        logger.info("mjpeg %s - %s", self.address_string(), fmt % args)

    def _authorized(self) -> bool:
        token = getattr(self.server, "token", None)
        if not token:
            return True

        header = self.headers.get("X-Stream-Token")
        if header and header == token:
            return True

        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query or "")
        provided = (qs.get("token") or [None])[0]
        return provided == token

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok")
            return

        if path == "/snapshot.jpg":
            if not self._authorized():
                self.send_response(401)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"unauthorized")
                return

            jpeg = self.server.buffer.get_latest(timeout_s=2.0)
            if not jpeg:
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"no_frame")
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpeg)
            return

        if path != self.server.stream_path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"not_found")
            return

        if not self._authorized():
            self.send_response(401)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"unauthorized")
            return

        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY}")
        self.end_headers()

        try:
            while True:
                jpeg = self.server.buffer.get_latest(timeout_s=2.0)
                if not jpeg:
                    continue

                self.wfile.write(f"--{_MJPEG_BOUNDARY}\r\n".encode("utf-8"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("utf-8"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            logger.exception("MJPEG client loop failed")
            return


def start_camera_stream_server(config: CameraStreamConfig) -> object | None:
    """Start a lightweight MJPEG HTTP server in a background thread.

    Returns the server instance when started, else None.
    """

    if not config.enabled:
        return None

    path = (config.path or "/mjpeg").strip() or "/mjpeg"
    if not path.startswith("/"):
        path = "/" + path

    buf = _FrameBuffer(config)
    if not buf.start():
        return None

    server = _MjpegServer(
        (str(config.host), int(config.port)),
        _MjpegHandler,
        buffer=buf,
        stream_path=path,
        token=config.token,
    )

    thread = threading.Thread(target=server.serve_forever, name="aerocommand-mjpeg-http", daemon=True)
    thread.start()

    logger.info("Camera MJPEG stream started on http://%s:%s%s", config.host, config.port, path)
    return server
