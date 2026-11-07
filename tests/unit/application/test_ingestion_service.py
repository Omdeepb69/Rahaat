"""Unit tests for ReportIngestionService."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from raahat.application.ingestion import (
    DisasterNotFoundError,
    ReportIngestionService,
)
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.outbox import DomainEvent


class TestReportIngestionServiceUnit:
    def test_disaster_not_found_raises(self) -> None:
        disaster_id = uuid.uuid4()
        session = MagicMock()
        session.get.return_value = None  # Disaster does not exist

        outbox = MagicMock()
        service = ReportIngestionService(session_factory=MagicMock(), outbox=outbox)

        submission = ReportSubmission(
            disaster_id=disaster_id,
            source_type=SourceType.WEB,
            raw_payload={"sos": "help"},
        )

        with pytest.raises(DisasterNotFoundError) as exc_info:
            service.ingest(submission, session=session)

        assert exc_info.value.disaster_id == disaster_id
        session.add.assert_not_called()
        outbox.publish.assert_not_called()

    def test_new_report_persisted_and_published(self) -> None:
        disaster_id = uuid.uuid4()
        session = MagicMock()
        session.get.return_value = DisasterModel(id=disaster_id, name="Test Disaster")
        # No existing report
        session.execute.return_value.scalar_one_or_none.return_value = None

        outbox = MagicMock()
        service = ReportIngestionService(session_factory=MagicMock(), outbox=outbox)

        submission = ReportSubmission(
            disaster_id=disaster_id,
            source_type=SourceType.SMS,
            source_identity="+919876543210",
            raw_payload={"message": "flood in area"},
            idempotency_key="sms-unique-001",
        )

        result = service.ingest(submission, session=session)

        assert result.is_duplicate is False
        assert result.disaster_id == disaster_id
        assert result.idempotency_key == "sms-unique-001"
        assert result.status == "pending"

        # Model added to session
        session.add.assert_called_once()
        added_model = session.add.call_args[0][0]
        assert isinstance(added_model, ReportModel)
        assert added_model.idempotency_key == "sms-unique-001"

        # Domain event published to outbox
        outbox.publish.assert_called_once()
        published_event = outbox.publish.call_args[0][0]
        assert isinstance(published_event, DomainEvent)
        assert published_event.event_type == "raahat.report.received"
        assert published_event.aggregate_type == "report"
        assert published_event.aggregate_id == result.report_id

        session.commit.assert_called_once()

    def test_existing_report_returns_duplicate_without_outbox_publish(self) -> None:
        disaster_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        session = MagicMock()
        session.get.return_value = DisasterModel(id=disaster_id, name="Test Disaster")

        existing_report = ReportModel(
            id=existing_id,
            disaster_id=disaster_id,
            source_type="sms",
            raw_payload={},
            idempotency_key="sms-duplicate-001",
            processing_status="pending",
        )
        session.execute.return_value.scalar_one_or_none.return_value = existing_report

        outbox = MagicMock()
        service = ReportIngestionService(session_factory=MagicMock(), outbox=outbox)

        submission = ReportSubmission(
            disaster_id=disaster_id,
            source_type=SourceType.SMS,
            raw_payload={},
            idempotency_key="sms-duplicate-001",
        )

        result = service.ingest(submission, session=session)

        assert result.is_duplicate is True
        assert result.report_id == existing_id
        assert result.idempotency_key == "sms-duplicate-001"

        # No new model added or outbox event emitted
        session.add.assert_not_called()
        outbox.publish.assert_not_called()

    def test_concurrent_integrity_error_recovers_as_duplicate(self) -> None:
        disaster_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        session = MagicMock()
        session.get.return_value = DisasterModel(id=disaster_id, name="Test Disaster")

        # Initial check returns None (race condition simulation)
        # Commit raises IntegrityError
        # Post-rollback check returns the concurrently inserted row
        concurrent_report = ReportModel(
            id=existing_id,
            disaster_id=disaster_id,
            source_type="sms",
            raw_payload={},
            idempotency_key="sms-race-001",
            processing_status="pending",
        )
        session.execute.return_value.scalar_one_or_none.side_effect = [
            None,
            concurrent_report,
        ]
        session.commit.side_effect = IntegrityError("statement", "params", Exception("unique violation"))

        outbox = MagicMock()
        service = ReportIngestionService(session_factory=MagicMock(), outbox=outbox)

        submission = ReportSubmission(
            disaster_id=disaster_id,
            source_type=SourceType.SMS,
            raw_payload={},
            idempotency_key="sms-race-001",
        )

        result = service.ingest(submission, session=session)

        assert result.is_duplicate is True
        assert result.report_id == existing_id
        session.rollback.assert_called_once()

