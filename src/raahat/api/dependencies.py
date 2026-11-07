"""FastAPI dependency injection providers."""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Generator, Optional

if TYPE_CHECKING:
    from raahat.application.incident_resolution import (
        IncidentResolutionService,
        IncidentReviewService,
    )
    from raahat.domain.evidence import EvidenceGraphService

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from raahat.adapters.channels.volunteer.service import DeviceSyncService
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


def get_session_factory() -> sessionmaker[Session]:
    global _SESSIONMAKER
    if _SESSIONMAKER is None:
        _SESSIONMAKER = get_sync_sessionmaker(get_engine())
    return _SESSIONMAKER


def get_db(
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> Generator[Session, None, None]:
    """Provide a database session per request."""
    with factory() as session:
        yield session


def get_ingestion_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> ReportIngestionService:
    """Provide ReportIngestionService instance."""
    return ReportIngestionService(session_factory=session_factory)


def get_location_verification_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> LocationVerificationService:
    """Provide LocationVerificationService instance."""
    return LocationVerificationService(session_factory=session_factory)


def get_device_sync_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> DeviceSyncService:
    """Provide DeviceSyncService instance."""
    return DeviceSyncService(session_factory=session_factory)


def get_evidence_graph_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> EvidenceGraphService:
    """Provide EvidenceGraphService instance."""
    from raahat.domain.evidence import EvidenceGraphService
    from raahat.infrastructure.database.repositories import PostgresEvidenceRepository

    repo = PostgresEvidenceRepository(session_factory=session_factory)
    return EvidenceGraphService(evidence_repo=repo, session_factory=session_factory)


def get_incident_resolution_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> IncidentResolutionService:
    """Provide IncidentResolutionService instance."""
    from raahat.application.incident_resolution import (
        ConservativeIncidentMatcher,
        ConservativeIncidentResolver,
        IncidentResolutionService,
    )

    matcher = ConservativeIncidentMatcher()
    resolver = ConservativeIncidentResolver()
    return IncidentResolutionService(
        matcher=matcher,
        resolver=resolver,
        session_factory=session_factory,
    )


def get_incident_review_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> IncidentReviewService:
    """Provide IncidentReviewService instance."""
    from raahat.application.incident_resolution import IncidentReviewService

    return IncidentReviewService(session_factory=session_factory)


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


def require_device_id(
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
) -> uuid.UUID:
    """Validate authenticated device identity from header."""
    if not x_device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device authentication required",
        )
    try:
        return uuid.UUID(x_device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid device UUID format",
        )
