"""Database engine and session management."""
from __future__ import annotations

import os
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_SYNC_URL = "postgresql://postgres:postgres@localhost:54329/raahat_test"
DEFAULT_ASYNC_URL = "postgresql+asyncpg://postgres:postgres@localhost:54329/raahat_test"


def get_sync_database_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_SYNC_URL)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def get_async_database_url() -> str:
    url = os.getenv("DATABASE_URL_ASYNC") or os.getenv("DATABASE_URL") or DEFAULT_ASYNC_URL
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://")
    return url


def create_sync_engine(url: str | None = None) -> Engine:
    target_url = url or get_sync_database_url()
    return create_engine(
        target_url,
        pool_pre_ping=True,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )


def create_async_engine_instance(url: str | None = None) -> AsyncEngine:
    target_url = url or get_async_database_url()
    return create_async_engine(
        target_url,
        pool_pre_ping=True,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )


def get_sync_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    eng = engine or create_sync_engine()
    return sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)


def get_async_sessionmaker(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    eng = engine or create_async_engine_instance()
    return async_sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    maker = get_sync_sessionmaker()
    with maker() as session:
        yield session


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    maker = get_async_sessionmaker()
    async with maker() as session:
        yield session
