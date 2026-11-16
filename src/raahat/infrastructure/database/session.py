"""Database engine and session factory."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Used only by tooling that runs without application settings (Alembic, tests).
DEFAULT_SYNC_URL = "postgresql://postgres:postgres@localhost:54330/raahat_test"


def get_sync_database_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_SYNC_URL)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def create_sync_engine(url: str | None = None) -> Engine:
    """Engine with a small bounded pool: the host has 8 GB and one API process.

    Each PostgreSQL backend costs several megabytes, so the pool is kept to
    what a single-process API and its request threads can use.
    """
    target = url or get_sync_database_url()
    if target.startswith("postgresql://"):
        target = target.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(
        target,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
        pool_timeout=10,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )


def get_sync_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or create_sync_engine(), autoflush=False, expire_on_commit=False)
