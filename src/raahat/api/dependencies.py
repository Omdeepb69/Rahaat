"""FastAPI dependency injection providers."""
from __future__ import annotations

import uuid
from typing import Generator, Optional

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from raahat.application.ingestion import ReportIngestionService
from raahat.application.location import LocationVerificationService
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


def get_location_verification_service() -> LocationVerificationService:
    """Provide LocationVerificationService instance."""
    return LocationVerificationService(session_factory=get_session_factory())


def require_dispatcher_id(
    x_dispatcher_id: Optional[str] = Header(None, alias="X-Dispatcher-Id"),
) -> uuid.UUID:
    """Validate authenticated dispatcher identity from header."""
    if not x_dispatcher_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated dispatcher identity required",
        )
    try:
        return uuid.UUID(x_dispatcher_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dispatcher UUID format",
        )
