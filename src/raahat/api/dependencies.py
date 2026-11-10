"""FastAPI dependency injection providers."""
from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING, Generator, Optional

if TYPE_CHECKING:
    from raahat.application.dispatch import DispatchService
    from raahat.application.events import EventBroadcaster
    from raahat.application.incident_resolution import (
        IncidentResolutionService,
        IncidentReviewService,
    )
    from raahat.application.resources import ResourceService
    from raahat.application.triage import IncidentTriageService
    from raahat.application.workflow import AutomatedAudioTriageWorkflow
    from raahat.domain.evidence import EvidenceGraphService
    from raahat.infrastructure.audit import AuditService
    from raahat.infrastructure.llm import LLMClient
    from raahat.infrastructure.speech import SpeechRecognizer, TTSSynthesizer
    from raahat.infrastructure.telephony import CallbackScheduler

from fastapi import Depends, Header, HTTPException, Query, status
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
_EVENT_BROADCASTER = None


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


def get_location_resolver(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
):
    """Provide PostGISGazetteerResolver instance backed by PostgreSQL."""
    from raahat.application.location import PostGISGazetteerResolver
    from raahat.infrastructure.database.repositories.landmark import PostgresLandmarkRepository

    repo = PostgresLandmarkRepository(session_factory=session_factory)
    return PostGISGazetteerResolver(landmark_repo=repo)


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


def get_incident_triage_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> IncidentTriageService:
    """Provide IncidentTriageService instance."""
    from raahat.application.triage import IncidentTriageService
    from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
    from raahat.infrastructure.database.repositories.evidence import PostgresEvidenceRepository

    evidence_repo = PostgresEvidenceRepository(session_factory)
    audit_repo = PostgresAuditRepository(session_factory)
    return IncidentTriageService(
        evidence_repo=evidence_repo,
        audit_repo=audit_repo,
        session_factory=session_factory,
    )


def get_dispatch_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> "DispatchService":
    """Provide DispatchService instance."""
    from raahat.application.dispatch import DispatchService
    from raahat.infrastructure.database.repositories.assignment import PostgresAssignmentRepository
    from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository

    assignment_repo = PostgresAssignmentRepository(session_factory)
    audit_repo = PostgresAuditRepository(session_factory)
    return DispatchService(
        assignment_repo=assignment_repo,
        audit_repo=audit_repo,
        session_factory=session_factory,
    )


def get_resource_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> ResourceService:
    """Provide ResourceService instance."""
    from raahat.application.resources import ResourceService
    from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
    from raahat.infrastructure.database.repositories.resource import PostgresResourceRepository

    resource_repo = PostgresResourceRepository(session_factory)
    audit_repo = PostgresAuditRepository(session_factory)
    return ResourceService(
        resource_repo=resource_repo,
        audit_repo=audit_repo,
        session_factory=session_factory,
    )


def get_audit_service(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> AuditService:
    """Provide AuditService instance."""
    from raahat.infrastructure.audit import AuditService, PostgresAuditRepository

    audit_repo = PostgresAuditRepository(session_factory)
    return AuditService(audit_repo=audit_repo, session_factory=session_factory)


def get_event_broadcaster() -> EventBroadcaster:
    """Provide singleton EventBroadcaster instance."""
    global _EVENT_BROADCASTER
    if _EVENT_BROADCASTER is None:
        from raahat.application.events import EventBroadcaster

        _EVENT_BROADCASTER = EventBroadcaster()
    return _EVENT_BROADCASTER


def get_callback_scheduler(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> CallbackScheduler:
    """Provide CallbackScheduler instance backed by PostgreSQL."""
    from raahat.infrastructure.database.repositories.callback import PostgresCallbackJobRepository
    from raahat.infrastructure.telephony import CallbackScheduler, StubTelephonyProvider

    repo = PostgresCallbackJobRepository(session_factory)
    provider = StubTelephonyProvider()
    return CallbackScheduler(repository=repo, provider=provider)


def get_speech_recognizer() -> "SpeechRecognizer":
    """Provide SpeechRecognizer instance (Gnani Prisma v3.0 by default)."""
    from raahat.infrastructure.speech import PrismaRecognizer

    return PrismaRecognizer()


def get_audio_triage_workflow(
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    broadcaster: EventBroadcaster = Depends(get_event_broadcaster),
    speech_recognizer: "SpeechRecognizer" = Depends(get_speech_recognizer),
) -> AutomatedAudioTriageWorkflow:
    """Provide AutomatedAudioTriageWorkflow instance backed by PostgreSQL, Gnani Prisma STT, and live SSE broadcaster."""
    from raahat.application.workflow import AutomatedAudioTriageWorkflow

    return AutomatedAudioTriageWorkflow(
        session_factory=session_factory,
        broadcaster=broadcaster,
        speech_recognizer=speech_recognizer,
    )


def get_tts_synthesizer() -> "TTSSynthesizer":
    """Provide TTSSynthesizer instance (Gnani Timbre by default)."""
    from raahat.infrastructure.speech import GnaniTimbreTTS

    return GnaniTimbreTTS()


def get_llm_client() -> "LLMClient":
    """Provide LLMClient instance (Evon, local transformer, or adaptive reasoning engine)."""
    from raahat.infrastructure.llm import create_llm_client

    return create_llm_client()


def require_dispatcher_id(
    x_dispatcher_id: Optional[str] = Header(None, alias="X-Dispatcher-Id"),
    dispatcher_id: Optional[str] = Query(None, alias="dispatcher_id"),
) -> uuid.UUID:
    """Validate authenticated dispatcher identity from header or query parameter."""
    raw_id = x_dispatcher_id or dispatcher_id
    if not raw_id:
        if os.getenv("DEMO_MODE", "false").lower() == "true":
            return uuid.UUID("00000000-0000-0000-0000-000000000001")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated dispatcher identity required",
        )
    try:
        return uuid.UUID(raw_id)
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
