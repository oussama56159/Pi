from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

import orjson

logger = logging.getLogger(__name__)


def write_connection_loss_backup(*, frames: list[dict], reason: str, path: str = "con_loss_backup") -> None:
    """Persist recent telemetry to a local file for post-incident debugging.

    This is intentionally simple: overwrite the same file each time so the
    latest incident is always available on-device.
    """

    payload = {
        "reason": reason,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "frames": frames,
    }

    target = Path(path)
    tmp = target.with_name(f"{target.name}.tmp")

    try:
        tmp.write_bytes(orjson.dumps(payload))
        tmp.replace(target)
    except Exception as exc:
        logger.warning("Failed writing connection-loss backup to %s: %s", target, exc)
