FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for pymavlink
RUN apt-get update ; apt-get install -y --no-install-recommends \
    gcc \
  ; rm -rf /var/lib/apt/lists/*

COPY shared_python /app/shared_python
COPY edge-agent /app/edge-agent

RUN pip install --no-cache-dir -e /app/shared_python ; \
    pip install --no-cache-dir -e "/app/edge-agent[camera]"

CMD ["aerocommand-edge-agent"]
