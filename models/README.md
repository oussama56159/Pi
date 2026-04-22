# Vision model weights

This folder is mounted into the backend `api-server` container as `/models` (see `docker-compose.yml`).

## Expected files

- `models/coco.pt` → mounted as `/models/coco.pt`
  - Used for **person/animal** detections.
- `models/fire.pt` → mounted as `/models/fire.pt`
  - Used for **fire/smoke** detections.

## Notes

- Model weight files are intentionally **not committed** to the repo (they are large and may have licensing constraints).
- If these files are missing, the backend will either fail to load the YOLO model or fall back to conservative heuristics (which do **not** detect person/animal/fire).

## Quick smoke test

Inside the running container you can verify the package is installed:

```bash
docker compose exec api-server python -c "from ultralytics import YOLO; print('ultralytics ok')"
```

To actually run detections you must provide the weight files above (or configure `VISION_MODEL_PATH*` to point at a valid model name/path).
