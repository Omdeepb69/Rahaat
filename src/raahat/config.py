"""Typed application settings, read once from the environment.

Every tunable the process reads lives here so that a missing or unsafe value is
caught at startup rather than at the first request that needs it.
"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Environment = Literal["development", "test", "production"]

_PLACEHOLDER_SECRETS = frozenset(
    {
        "",
        "change-me",
        "changeme",
        "raahat-dev-secret-change-in-production-do-not-use",
    }
)
MIN_SECRET_LENGTH = 32


class ConfigurationError(RuntimeError):
    """Raised at startup when the environment cannot be run safely."""


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().rstrip("/") for part in raw.split(",") if part.strip())


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional(name: str) -> Optional[str]:
    raw = os.getenv(name, "").strip()
    return raw or None


class Settings(BaseModel):
    """Immutable snapshot of process configuration."""

    model_config = ConfigDict(frozen=True)

    environment: Environment = "development"
    database_url: str
    secret_key: str
    secret_key_is_ephemeral: bool = False

    access_token_ttl_seconds: int = Field(default=30 * 60, ge=60)
    session_max_seconds: int = Field(default=12 * 60 * 60, ge=300)

    cors_allowed_origins: tuple[str, ...] = ()
    trust_forwarded_headers: bool = False
    public_intake_enabled: bool = False

    max_request_bytes: int = Field(default=1 * 1024 * 1024, ge=1024)
    max_audio_upload_bytes: int = Field(default=15 * 1024 * 1024, ge=1024)
    audio_storage_dir: Path = Path("storage/audio")

    login_rate_per_minute: int = Field(default=10, ge=1)
    api_rate_per_minute: int = Field(default=600, ge=10)
    public_rate_per_minute: int = Field(default=10, ge=1)
    max_failed_logins: int = Field(default=5, ge=1)
    lockout_seconds: int = Field(default=15 * 60, ge=30)

    # Speech-to-text (Gnani Prisma, served from api.vachana.ai)
    gnani_api_key: Optional[str] = None
    prisma_endpoint: str = "https://api.vachana.ai/stt/v3"
    # Text-to-speech (Gnani Timbre) for the guided voice call; same key.
    timbre_endpoint: str = "https://api.vachana.ai/api/v1/tts/inference"
    timbre_model: str = "timbre-v3.0"
    timbre_voice: str = "Shivani"
    # Requests per minute from one address during a guided call (turns and prompt audio).
    voice_call_rate_per_minute: int = Field(default=90, ge=10)

    # Extraction / translation model
    llm_provider: Literal["none", "evon", "gemini"] = "none"
    evon_api_base: Optional[str] = None
    evon_api_key: Optional[str] = None
    evon_model: str = "gnani/gnani-evon-v3.3-30B-A3B"
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-flash-lite"

    # Geospatial services
    geocoder_provider: Literal["none", "nominatim"] = "none"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    geocoder_country_codes: str = "in"
    routing_provider: Literal["none", "osrm"] = "none"
    osrm_base_url: Optional[str] = None
    http_user_agent: str = "RAAHAT/0.3 (self-hosted emergency coordination)"

    # External situational data
    cap_alert_feed_url: Optional[str] = None

    # Duplicate detection. A threshold above 1.0 disables automatic linking:
    # every match is held for operator review.
    dedup_review_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    dedup_auto_link_threshold: float = Field(default=1.01, ge=0.0)

    worker_tick_seconds: float = Field(default=2.0, gt=0)
    worker_batch_size: int = Field(default=5, ge=1, le=50)
    worker_stale_after_seconds: int = Field(default=30, ge=5)
    provider_timeout_seconds: float = Field(default=30.0, gt=0)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def load_settings() -> Settings:
    """Build settings from the environment, validating production safety."""
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if environment not in {"development", "test", "production"}:
        raise ConfigurationError(
            f"ENVIRONMENT must be development, test or production (got {environment!r})"
        )

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL is required")
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    secret = os.getenv("RAAHAT_SECRET_KEY", "").strip()
    ephemeral = False
    if secret in _PLACEHOLDER_SECRETS or len(secret) < MIN_SECRET_LENGTH:
        if environment == "production":
            raise ConfigurationError(
                "RAAHAT_SECRET_KEY must be set to a random value of at least "
                f"{MIN_SECRET_LENGTH} characters in production. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        # Outside production an unset key is replaced by a per-process random
        # one: sessions do not survive a restart, and nothing guessable is used.
        secret = secrets.token_urlsafe(48)
        ephemeral = True

    origins = _split_csv(os.getenv("CORS_ALLOWED_ORIGINS", ""))
    if "*" in origins:
        raise ConfigurationError(
            "CORS_ALLOWED_ORIGINS must list exact origins; '*' is not accepted"
        )

    llm_provider = os.getenv("LLM_PROVIDER", "none").strip().lower() or "none"
    if llm_provider not in {"none", "evon", "gemini"}:
        raise ConfigurationError("LLM_PROVIDER must be none, evon or gemini")

    geocoder = os.getenv("GEOCODER_PROVIDER", "none").strip().lower() or "none"
    if geocoder not in {"none", "nominatim"}:
        raise ConfigurationError("GEOCODER_PROVIDER must be none or nominatim")

    routing = os.getenv("ROUTING_PROVIDER", "none").strip().lower() or "none"
    if routing not in {"none", "osrm"}:
        raise ConfigurationError("ROUTING_PROVIDER must be none or osrm")

    values: dict[str, object] = {
        "environment": environment,
        "database_url": database_url,
        "secret_key": secret,
        "secret_key_is_ephemeral": ephemeral,
        "cors_allowed_origins": origins,
        "trust_forwarded_headers": _flag("TRUST_FORWARDED_HEADERS"),
        "public_intake_enabled": _flag("PUBLIC_INTAKE_ENABLED"),
        "gnani_api_key": _optional("GNANI_API_KEY_TTS_STT") or _optional("GNANI_API_KEY"),
        "llm_provider": llm_provider,
        "evon_api_base": _optional("EVON_API_BASE"),
        "evon_api_key": _optional("EVON_API_KEY"),
        "gemini_api_key": _optional("GEMINI_API_KEY"),
        "geocoder_provider": geocoder,
        "routing_provider": routing,
        "osrm_base_url": _optional("OSRM_BASE_URL"),
        "cap_alert_feed_url": _optional("CAP_ALERT_FEED_URL"),
    }

    passthrough = {
        "ACCESS_TOKEN_TTL_SECONDS": ("access_token_ttl_seconds", int),
        "SESSION_MAX_SECONDS": ("session_max_seconds", int),
        "MAX_REQUEST_BYTES": ("max_request_bytes", int),
        "MAX_AUDIO_UPLOAD_BYTES": ("max_audio_upload_bytes", int),
        "AUDIO_STORAGE_DIR": ("audio_storage_dir", Path),
        "LOGIN_RATE_PER_MINUTE": ("login_rate_per_minute", int),
        "API_RATE_PER_MINUTE": ("api_rate_per_minute", int),
        "PUBLIC_RATE_PER_MINUTE": ("public_rate_per_minute", int),
        "MAX_FAILED_LOGINS": ("max_failed_logins", int),
        "LOCKOUT_SECONDS": ("lockout_seconds", int),
        "PRISMA_ENDPOINT": ("prisma_endpoint", str),
        "TIMBRE_ENDPOINT": ("timbre_endpoint", str),
        "TIMBRE_MODEL": ("timbre_model", str),
        "TIMBRE_VOICE": ("timbre_voice", str),
        "VOICE_CALL_RATE_PER_MINUTE": ("voice_call_rate_per_minute", int),
        "EVON_MODEL": ("evon_model", str),
        "GEMINI_MODEL": ("gemini_model", str),
        "NOMINATIM_BASE_URL": ("nominatim_base_url", str),
        "GEOCODER_COUNTRY_CODES": ("geocoder_country_codes", str),
        "HTTP_USER_AGENT": ("http_user_agent", str),
        "DEDUP_REVIEW_THRESHOLD": ("dedup_review_threshold", float),
        "DEDUP_AUTO_LINK_THRESHOLD": ("dedup_auto_link_threshold", float),
        "WORKER_TICK_SECONDS": ("worker_tick_seconds", float),
        "WORKER_BATCH_SIZE": ("worker_batch_size", int),
        "WORKER_STALE_AFTER_SECONDS": ("worker_stale_after_seconds", int),
        "PROVIDER_TIMEOUT_SECONDS": ("provider_timeout_seconds", float),
    }
    for env_name, (field, caster) in passthrough.items():
        raw = os.getenv(env_name, "").strip()
        if not raw:
            continue
        try:
            values[field] = caster(raw)
        except ValueError as exc:
            raise ConfigurationError(f"{env_name} has an invalid value: {raw!r}") from exc

    return Settings(**values)  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Tests clear the cache after changing the environment."""
    return load_settings()
