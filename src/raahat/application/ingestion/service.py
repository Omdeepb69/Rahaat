"""Report Ingestion Service.

Responsible for atomic persistence of incoming distress reports and their
corresponding transactional outbox event. Enforces idempotency via
(disaster_id, idempotency_key) to ensure no duplicate processing.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.reports.report import ReportSubmission
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.outbox import DomainEvent, EventOutbox, PostgresEventOutbox

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for report ingestion failures."""


class DisasterNotFoundError(IngestionError):
    """Raised when the specified disaster_id does not exist."""

    def __init__(self, disaster_id: uuid.UUID) -> None:
        super().__init__(f"Disaster with ID '{disaster_id}' not found.")
        self.disaster_id = disaster_id


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of an ingestion attempt."""

    report_id: uuid.UUID
    disaster_id: uuid.UUID
    is_duplicate: bool
    status: str
    idempotency_key: str
    received_at: datetime


class ReportIngestionService:
    """Application service for atomic report ingestion and outbox publication."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        outbox: Optional[EventOutbox] = None,
    ) -> None:
        self._session_factory = session_factory
        self._outbox = outbox or PostgresEventOutbox()

    def ingest(
        self,
        submission: ReportSubmission,
        session: Optional[Session] = None,
    ) -> IngestionResult:
        """Ingest a report submission with strict idempotency and outbox publication.

        If ``session`` is provided, executes within that session's transaction
        (caller controls commit/rollback). Otherwise, acquires a new session from
        ``session_factory`` and manages the transaction boundary.
        """
        if session is not None:
            return self._execute_ingest(session, submission)

        with self._session_factory() as managed_session:
            return self._execute_ingest(managed_session, submission)

    def _execute_ingest(
        self,
        session: Session,
        submission: ReportSubmission,
    ) -> IngestionResult:
        # 1. Validate disaster existence
        disaster = session.get(DisasterModel, submission.disaster_id)
        if disaster is None:
            raise DisasterNotFoundError(submission.disaster_id)

        # 2. Convert submission to domain report with computed idempotency key
        report = submission.to_report()

        # 3. Check for existing report with this (disaster_id, idempotency_key)
        existing_stmt = select(ReportModel).where(
            ReportModel.disaster_id == report.disaster_id,
            ReportModel.idempotency_key == report.idempotency_key,
        )
        existing = session.execute(existing_stmt).scalar_one_or_none()
        if existing is not None:
            logger.info(
                "Duplicate report received",
                extra={
                    "report_id": str(existing.id),
                    "disaster_id": str(existing.disaster_id),
                    "idempotency_key": existing.idempotency_key,
                },
            )
            return IngestionResult(
                report_id=existing.id,
                disaster_id=existing.disaster_id,
                is_duplicate=True,
                status=existing.processing_status,
                idempotency_key=existing.idempotency_key,
                received_at=existing.received_at,
            )

        # 4. Create database model
        report_row = ReportModel(
            id=report.id,
            disaster_id=report.disaster_id,
            source_type=report.source_type.value,
            source_event_id=report.source_event_id,
            source_identity=report.source_identity,
            device_id=report.device_id,
            channel_reference=report.channel_reference,
            raw_payload=report.raw_payload,
            received_at=report.received_at,
            client_created_at=report.client_created_at,
            language_code=report.language_code,
            processing_status=report.processing_status.value,
            idempotency_key=report.idempotency_key,
        )
        session.add(report_row)

        # 5. Atomically publish domain event to transactional outbox
        event = DomainEvent(
            event_type="raahat.report.received",
            aggregate_type="report",
            aggregate_id=report.id,
            payload={
                "report_id": str(report.id),
                "disaster_id": str(report.disaster_id),
                "source_type": report.source_type.value,
                "source_identity": report.source_identity,
                "channel_reference": report.channel_reference,
                "idempotency_key": report.idempotency_key,
                "received_at": report.received_at.isoformat(),
            },
            occurred_at=report.received_at,
        )
        self._outbox.publish(event, session)

        # 6. Commit transaction, catching concurrent uniqueness conflicts
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # Handle potential race-condition duplicate
            race_existing = session.execute(existing_stmt).scalar_one_or_none()
            if race_existing is not None:
                return IngestionResult(
                    report_id=race_existing.id,
                    disaster_id=race_existing.disaster_id,
                    is_duplicate=True,
                    status=race_existing.processing_status,
                    idempotency_key=race_existing.idempotency_key,
                    received_at=race_existing.received_at,
                )
            raise

        logger.info(
            "Report ingested successfully",
            extra={
                "report_id": str(report.id),
                "disaster_id": str(report.disaster_id),
                "idempotency_key": report.idempotency_key,
            },
        )
        return IngestionResult(
            report_id=report.id,
            disaster_id=report.disaster_id,
            is_duplicate=False,
            status=report.processing_status.value,
            idempotency_key=report.idempotency_key,
            received_at=report.received_at,
        )
