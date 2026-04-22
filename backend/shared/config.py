"""
Centralized configuration loaded from environment variables.
Each microservice imports and extends this base config.
"""
from __future__ import annotations

from functools import lru_cache
import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class BaseServiceSettings(BaseSettings):
    """Base settings shared by all microservices."""

    # ── Service identity ──
    SERVICE_NAME: str = "aerocommand"
    SERVICE_VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Dev-only DB bootstrap ──
    AUTO_CREATE_DB: bool = False

    # ── PostgreSQL ──
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "aerocommand"
    POSTGRES_PASSWORD: str = "aerocommand_secret"
    POSTGRES_DB: str = "aerocommand"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── MQTT (EMQX) ──
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_BROKER_WS_PORT: int = 8083
    MQTT_USERNAME: str | None = None
    MQTT_PASSWORD: str | None = None
    MQTT_CLIENT_ID_PREFIX: str = "aerocommand"
    MQTT_QOS: int = Field(default=1, ge=0, le=2)
    MQTT_KEEPALIVE: int = 60

    # ── JWT ──
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_use_openssl_rand_hex_64"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:5173",
            "https://pi-group.vercel.app",
        ]
    )

    # Optional regex for origin matching (useful for Vercel preview domains)
    CORS_ORIGIN_REGEX: str | None = None

    # ── Email (SMTP) ──
    # Used for server-side email sending (e.g., password recovery requests from the web UI).
    SUPPORT_EMAIL: str = "touati.oussama@esprit.tn"

    # NOTE: Do not hardcode SMTP credentials in source control.
    # Configure these via environment variables / Docker secrets.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_STARTTLS: bool = True
    SMTP_USE_SSL: bool = False

    @field_validator("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        # Allow env var formats:
        # - JSON: ["https://app.vercel.app", "http://localhost:3000"]
        # - CSV:  https://app.vercel.app,http://localhost:3000
        if value is None:
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    return [str(x) for x in parsed]
                except Exception:
                    pass
            return [part.strip() for part in raw.split(",") if part.strip()]
        return value

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache
def get_base_settings() -> BaseServiceSettings:
    return BaseServiceSettings()

