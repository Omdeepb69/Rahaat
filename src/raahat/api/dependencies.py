"""FastAPI dependency injection providers."""
from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from raahat.application.ingestion import ReportIngestionService
from raahat.infrastructure.database.session import (
    create_sync_engine,
    get_sync_sessionmaker,
)

_ENGINE = None
_SESSIONMAKER = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_sync_engine()
    return _ENGINE


def get_session_factory():
    global _SESSIONMAKER
    if _SESSIONMAKER is None:
        _SESSIONMAKER = get_sync_sessionmaker(get_engine())
    return _SESSIONMAKER


def get_db() -> Generator[Session, None, None]:
    """Provide a database session per request."""
    factory = get_session_factory()
    with factory() as session:
        yield session


def get_ingestion_service() -> ReportIngestionService:
    """Provide ReportIngestionService instance."""
    return ReportIngestionService(session_factory=get_session_factory())

