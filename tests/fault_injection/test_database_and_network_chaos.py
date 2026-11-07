"""Fault injection tests for database disconnections, network outages, and duplicate sync requests."""
from __future__ import annotations

import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from field_app import (
    DatabaseManager,
    OfflineReportDraft,
    OfflineSyncQueue,
    SyncStatus,
)
from field_app.models import SyncBatch, SyncReportItem
from raahat.adapters.channels.volunteer.service import DeviceSyncService
from raahat.application.ingestion.service import ReportIngestionService
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models import DisasterModel
from raahat.infrastructure.database.models.sync import SyncCursorModel
from raahat.workers.sync_worker import SyncWorker


def _sample_submission(disaster_id: uuid.UUID) -> ReportSubmission:
    return ReportSubmission(
        disaster_id=disaster_id,
        source_type=SourceType.WEB,
        source_identity="+919876543210",
        raw_payload={"text": "Flood water entering ground floor"},
        language_code="hi",
    )


def test_database_disconnection_rejects_without_acknowledgement() -> None:
    """CRITICAL SAFETY INVARIANT:

    If PostgreSQL is disconnected/unreachable, ingestion MUST fail diagnosably
    and NEVER return an IngestionResult acknowledging an unpersisted report.
    """
    mock_session_factory = MagicMock()
    mock_session = MagicMock()
    mock_session_factory.return_value.__enter__.return_value = mock_session

    # Simulate database connection refusal during query/insert
    mock_session.get.side_effect = OperationalError(
        "could not connect to server: Connection refused\nIs the server running on host 'localhost'?",
        params=None,
        orig=Exception("Connection refused"),
    )

    service = ReportIngestionService(session_factory=mock_session_factory)
    disaster_id = uuid.uuid4()
    submission = _sample_submission(disaster_id)

    with pytest.raises(OperationalError) as exc_info:
        service.ingest(submission)

    assert "Connection refused" in str(exc_info.value)
    # Verify session rollback was invoked
    mock_session_factory.return_value.__exit__.assert_called()


def test_offline_field_device_queues_during_internet_outage() -> None:
    """Scenario: Internet connection drops in disaster zone.

    The field volunteer client must store reports safely in local SQLite with monotonic
    sequence numbers and survive device restarts.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "field_agent.db")
        db = DatabaseManager(db_path)
        device_id = uuid.uuid4()
        disaster_id = uuid.uuid4()
        queue = OfflineSyncQueue(device_id=device_id, db=db, device_name="Volunteer-Phone-1")

        # Volunteer logs reports offline
        r1 = queue.enqueue_report(
            OfflineReportDraft(
                disaster_id=disaster_id,
                raw_payload={"landmark": "Near temple", "headcount": 4},
                source_identity="Volunteer John",
            )
        )
        r2 = queue.enqueue_report(
            OfflineReportDraft(
                disaster_id=disaster_id,
                raw_payload={"landmark": "Govt High School", "headcount": 12},
                source_identity="Volunteer John",
            )
        )

        assert r1.sequence == 1
        assert r2.sequence == 2
        assert r1.sync_status == SyncStatus.LOCALLY_SAVED
        assert r2.sync_status == SyncStatus.LOCALLY_SAVED

        # Simulate device restart / power cycle by reopening DB connection
        db_restarted = DatabaseManager(db_path)
        queue_restarted = OfflineSyncQueue(device_id=device_id, db=db_restarted, device_name="Volunteer-Phone-1")
        pending = queue_restarted.list_reports(status=SyncStatus.LOCALLY_SAVED)

        assert len(pending) == 2
        assert [p.sequence for p in pending] == [1, 2]


def _make_sync_item(sequence: int, disaster_id: uuid.UUID) -> SyncReportItem:
    """Create a valid SyncReportItem with the correct schema."""
    return SyncReportItem(
        event_id=uuid.uuid4(),
        sequence=sequence,
        disaster_id=disaster_id,
        raw_payload={"text": f"Distress report {sequence}"},
        client_created_at=datetime.now(timezone.utc),
        idempotency_key=f"volunteer:test-device:seq:{sequence}",
    )


def test_duplicate_sync_requests_idempotently_suppressed() -> None:
    """Scenario: Field device submits a sync batch, but ACK packet is dropped on flaky network.

    Device retries transmitting the exact same batch. Server must detect duplicates,
    return a valid SyncAck, and create zero duplicate report records.
    """
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()

    mock_session_factory = MagicMock()
    mock_session = MagicMock()
    mock_session_factory.return_value.__enter__.return_value = mock_session

    # Disaster exists
    disaster_model = DisasterModel(id=disaster_id, name="Kerala Flood", disaster_type="flood")
    mock_session.get.return_value = disaster_model

    cursor = SyncCursorModel(
        device_id=device_id,
        last_sequence=0,
        last_synced_at=datetime.now(timezone.utc),
    )
    mock_session.query.return_value.filter_by.return_value.first.return_value = cursor

    # Ingestion service double
    ingestion_service = MagicMock()

    sync_service = DeviceSyncService(
        session_factory=mock_session_factory,
        ingestion_service=ingestion_service,
    )

    batch = SyncBatch(
        device_id=device_id,
        from_sequence=1,
        to_sequence=2,
        items=[
            _make_sync_item(1, disaster_id),
            _make_sync_item(2, disaster_id),
        ],
    )

    # 1. First sync attempt: both items are newly accepted
    ingestion_service.ingest.side_effect = [
        MagicMock(is_duplicate=False),
        MagicMock(is_duplicate=False),
    ]

    ack1 = sync_service.sync_batch(device_id, batch)
    assert ack1.accepted_count == 2
    assert ack1.duplicate_count == 0
    assert ack1.acknowledged_sequence == 2

    # 2. Network retransmit: same batch sent again
    ingestion_service.ingest.side_effect = [
        MagicMock(is_duplicate=True),
        MagicMock(is_duplicate=True),
    ]

    ack2 = sync_service.sync_batch(device_id, batch)
    assert ack2.accepted_count == 0
    assert ack2.duplicate_count == 2
    assert ack2.acknowledged_sequence == 2


def test_sync_sequence_gap_detection() -> None:
    """Scenario: Device reports sequence jump (e.g. seq 1 received, then seq 4 received).

    SyncWorker must flag missing sequences (2 and 3) diagnosably.
    """
    device_id = uuid.uuid4()
    mock_session_factory = MagicMock()
    mock_session = MagicMock()
    mock_session_factory.return_value.__enter__.return_value = mock_session

    cursor = SyncCursorModel(
        device_id=device_id,
        last_sequence=4,
        last_synced_at=datetime.now(timezone.utc),
    )
    mock_session.query.return_value.filter_by.return_value.first.return_value = cursor

    # Reports in database have channel_references with sequence 1 and 4 (missing 2 and 3)
    mock_session.execute.return_value.scalars.return_value.all.return_value = [
        "batch:abc:seq:1",
        "batch:abc:seq:4",
    ]

    worker = SyncWorker(session_factory=mock_session_factory)
    audit = worker.audit_device_sequences(device_id)

    assert audit["is_continuous"] is False
    assert audit["missing_sequences"] == [2, 3]
    assert audit["received_count"] == 2
