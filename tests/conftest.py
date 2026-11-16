"""Shared test configuration.

Tests run against a dedicated PostgreSQL/PostGIS database named by
``DATABASE_URL`` (default: the throwaway test container on port 54330). The
schema is migrated to head once per session. Every row these tests create is a
test fixture in an isolated test database; nothing here touches operational
data.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:54330/raahat_test")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("RAAHAT_SECRET_KEY", "test-only-secret-key-not-used-anywhere-else-000")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://frontend.test")
os.environ.setdefault("LOGIN_RATE_PER_MINUTE", "1000")
os.environ.setdefault("PUBLIC_RATE_PER_MINUTE", "1000")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "src/raahat/infrastructure/database/migrations"))
    command.upgrade(config, "head")
