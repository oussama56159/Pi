# ─── AeroCommand Backend ───
# Multi-stage Python build for FastAPI microservices
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ─── Stage 1: Dependencies ───
FROM base AS deps

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
        libglib2.0-0 libsm6 libxext6 libxrender1 libxcb1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Force CPU-only PyTorch wheels to avoid downloading CUDA/NVIDIA packages.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision
RUN pip install --no-cache-dir \
    fastapi[standard] \
    uvicorn[standard] \
    sqlalchemy[asyncio] \
    asyncpg \
    alembic \
    pydantic \
    pydantic-settings \
    python-jose[cryptography] \
    passlib[bcrypt] \
    "bcrypt<4.0" \
    aiomqtt \
    redis[hiredis] \
    prometheus-client \
    httpx \
    python-multipart \
    orjson \
    numpy \
    opencv-python-headless \
    ultralytics

# ─── Stage 2: Production ───
FROM base AS production

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
        libglib2.0-0 libsm6 libxext6 libxrender1 libxcb1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r aerocommand && useradd -r -g aerocommand -d /app aerocommand

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY . /app/backend
ENV PYTHONPATH=/app

USER aerocommand

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

