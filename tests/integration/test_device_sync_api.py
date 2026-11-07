"""Integration tests for device synchronization endpoint and sync worker."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from field_app import (
    DatabaseManager,
    OfflineReportDraft,
    OfflineSyncQueue,
    SyncAck,
    SyncBatch,
    SyncReportItem,
    SyncStatus,
)
from raahat.api.app import create_app
from raahat.api.dependencies import get_session_factory
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models import (
    DisasterModel,
    OutboxEventModel,
    ReportModel,
    SyncCursorModel,
)
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine(TEST_DB_URL)
    return get_sync_sessionmaker(engine)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        session.query(OutboxEventModel).delete()
        session.query(ReportModel).delete()
        session.query(SyncCursorModel).delete()
        session.query(DisasterModel).delete()
        session.commit()
        yield session


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def test_disaster(db_session: Session) -> DisasterModel:
    disaster = DisasterModel(
        id=uuid.uuid4(),
        name="Kerala Floods 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()
    db_session.refresh(disaster)
    return disaster


def _make_sync_batch(
    device_id: uuid.UUID,
    disaster_id: uuid.UUID,
    sequences: list[int],
    batch_id: uuid.UUID | None = None,
) -> SyncBatch:
    items = []
    for seq in sequences:
        item = SyncReportItem(
            event_id=uuid.uuid4(),
            sequence=seq,
            disaster_id=disaster_id,
            raw_payload={
                "urgency": "critical",
                "trapped_count": seq * 2,
                "needs": ["rescue", "water"],
            },
            client_created_at=datetime(2026, 8, 15, 10, seq, 0, tzinfo=timezone.utc),
            idempotency_key=f"volunteer:{device_id}:{seq}",
            source_identity="Volunteer-Alpha",
            language_code="ml",
        )
        items.append(item)

    return SyncBatch(
        device_id=device_id,
        batch_id=batch_id or uuid.uuid4(),
        from_sequence=min(sequences),
        to_sequence=max(sequences),
        items=items,
    )


def test_sync_batch_success(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    device_id = uuid.uuid4()
    batch = _make_sync_batch(device_id, test_disaster.id, [1, 2, 3])

    response = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )

    assert response.status_code == 200, response.text
    ack = response.json()
    assert ack["device_id"] == str(device_id)
    assert ack["batch_id"] == str(batch.batch_id)
    assert ack["acknowledged_sequence"] == 3
    assert ack["accepted_count"] == 3
    assert ack["duplicate_count"] == 0
    assert "server_synced_at" in ack

    # 1. Verify database reports
    db_session.expire_all()
    reports = (
        db_session.query(ReportModel)
        .filter_by(device_id=device_id)
        .order_by(ReportModel.client_created_at.asc())
        .all()
    )
    assert len(reports) == 3
    for idx, report in enumerate(reports, start=1):
        assert report.source_type == SourceType.VOLUNTEER.value
        assert report.disaster_id == test_disaster.id
        assert report.idempotency_key == f"volunteer:{device_id}:{idx}"
        assert report.channel_reference == f"batch:{batch.batch_id}:seq:{idx}"
        assert report.client_created_at == datetime(2026, 8, 15, 10, idx, 0, tzinfo=timezone.utc)
        assert report.received_at is not None
        assert report.raw_payload["trapped_count"] == idx * 2

    # 2. Verify sync cursor in DB
    cursor = db_session.query(SyncCursorModel).filter_by(device_id=device_id).first()
    assert cursor is not None
    assert cursor.last_sequence == 3
    assert cursor.sync_metadata["accepted_count"] == 3
    assert cursor.sync_metadata["duplicate_count"] == 0
    assert cursor.sync_metadata["last_batch_id"] == str(batch.batch_id)

    # 3. Verify transactional outbox events
    report_events = (
        db_session.query(OutboxEventModel)
        .filter_by(event_type="raahat.report.received")
        .all()
    )
    assert len(report_events) == 3

    device_events = (
        db_session.query(OutboxEventModel)
        .filter_by(event_type="raahat.device.synced")
        .all()
    )
    assert len(device_events) == 1
    assert device_events[0].aggregate_id == device_id
    assert device_events[0].payload["to_sequence"] == 3
    assert device_events[0].payload["accepted_count"] == 3


def test_sync_batch_retransmission_is_idempotent(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    device_id = uuid.uuid4()
    batch = _make_sync_batch(device_id, test_disaster.id, [1, 2])

    # First transmission
    resp1 = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert resp1.status_code == 200
    assert resp1.json()["accepted_count"] == 2
    assert resp1.json()["duplicate_count"] == 0

    # Retransmission of identical batch
    resp2 = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert resp2.status_code == 200
    ack2 = resp2.json()
    assert ack2["device_id"] == str(device_id)
    assert ack2["batch_id"] == str(batch.batch_id)
    assert ack2["acknowledged_sequence"] == 2
    assert ack2["accepted_count"] == 0
    assert ack2["duplicate_count"] == 2

    # Verify no duplicate reports created
    db_session.expire_all()
    reports = db_session.query(ReportModel).filter_by(device_id=device_id).all()
    assert len(reports) == 2

    # Verify report.received outbox events did not duplicate
    report_events = (
        db_session.query(OutboxEventModel)
        .filter_by(event_type="raahat.report.received")
        .all()
    )
    assert len(report_events) == 2

    # Verify cursor remains at sequence 2
    cursor = db_session.query(SyncCursorModel).filter_by(device_id=device_id).first()
    assert cursor is not None
    assert cursor.last_sequence == 2


def test_sync_batch_partial_overlap(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    device_id = uuid.uuid4()

    # Batch 1: sequences [1, 2]
    batch1 = _make_sync_batch(device_id, test_disaster.id, [1, 2])
    resp1 = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch1.model_dump(mode="json"),
    )
    assert resp1.status_code == 200
    assert resp1.json()["accepted_count"] == 2
    assert resp1.json()["duplicate_count"] == 0

    # Batch 2: sequences [2, 3] (sequence 2 is retransmitted overlap, sequence 3 is new)
    batch2 = _make_sync_batch(device_id, test_disaster.id, [2, 3])
    resp2 = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch2.model_dump(mode="json"),
    )
    assert resp2.status_code == 200
    ack2 = resp2.json()
    assert ack2["accepted_count"] == 1
    assert ack2["duplicate_count"] == 1
    assert ack2["acknowledged_sequence"] == 3

    # Total reports in database should be exactly 3
    db_session.expire_all()
    reports = db_session.query(ReportModel).filter_by(device_id=device_id).all()
    assert len(reports) == 3

    # Cursor must be advanced to sequence 3
    cursor = db_session.query(SyncCursorModel).filter_by(device_id=device_id).first()
    assert cursor is not None
    assert cursor.last_sequence == 3


def test_sync_device_authentication(
    client: TestClient,
    test_disaster: DisasterModel,
) -> None:
    device_id = uuid.uuid4()
    batch = _make_sync_batch(device_id, test_disaster.id, [1])

    # 1. Missing X-Device-Id header
    resp_missing = client.post(
        "/api/v1/devices/sync",
        json=batch.model_dump(mode="json"),
    )
    assert resp_missing.status_code == 401
    assert "Device authentication required" in resp_missing.json()["detail"]

    # 2. Malformed X-Device-Id header
    resp_malformed = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": "not-a-valid-uuid"},
        json=batch.model_dump(mode="json"),
    )
    assert resp_malformed.status_code == 400
    assert "Invalid device UUID format" in resp_malformed.json()["detail"]

    # 3. Mismatched X-Device-Id header vs batch.device_id
    different_device_id = uuid.uuid4()
    resp_mismatched = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(different_device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert resp_mismatched.status_code == 403
    assert "Authenticated device ID does not match batch payload" in resp_mismatched.json()["detail"]


def test_sync_disaster_not_found(client: TestClient) -> None:
    device_id = uuid.uuid4()
    non_existent_disaster_id = uuid.uuid4()
    batch = _make_sync_batch(device_id, non_existent_disaster_id, [1])

    response = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert response.status_code == 404
    assert str(non_existent_disaster_id) in response.json()["detail"]


def test_get_device_cursor(
    client: TestClient,
    test_disaster: DisasterModel,
) -> None:
    device_id = uuid.uuid4()

    # 1. Non-existent device cursor returns 404
    resp_not_found = client.get(f"/api/v1/devices/{device_id}/cursor")
    assert resp_not_found.status_code == 404

    # 2. Sync a batch
    batch = _make_sync_batch(device_id, test_disaster.id, [1, 2])
    sync_resp = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert sync_resp.status_code == 200

    # 3. Retrieve cursor returns 200 with cursor details
    resp_cursor = client.get(f"/api/v1/devices/{device_id}/cursor")
    assert resp_cursor.status_code == 200
    data = resp_cursor.json()
    assert data["device_id"] == str(device_id)
    assert data["last_sequence"] == 2
    assert "last_synced_at" in data
    assert data["sync_metadata"]["accepted_count"] == 2


def test_field_app_offline_queue_client_server_roundtrip(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    """End-to-end test from offline SQLite field app queue to server sync API and acknowledgement."""
    device_id = uuid.uuid4()
    db = DatabaseManager(":memory:")
    queue = OfflineSyncQueue(device_id=device_id, db=db, device_name="Volunteer-Tablet-1")

    # 1. Field volunteer records reports offline
    draft1 = OfflineReportDraft(
        disaster_id=test_disaster.id,
        raw_payload={"location": "Sector 4", "flood_depth_cm": 120},
        source_identity="Volunteer Priya",
        language_code="hi",
    )
    draft2 = OfflineReportDraft(
        disaster_id=test_disaster.id,
        raw_payload={"location": "Sector 5", "medical_emergency": True},
        source_identity="Volunteer Priya",
        language_code="hi",
    )
    queue.enqueue_report(draft1)
    queue.enqueue_report(draft2)

    assert queue.get_current_sequence() == 2
    counts_before = queue.get_sync_counts()
    assert counts_before[SyncStatus.LOCALLY_SAVED.value] == 2

    # 2. Prepare outbound batch
    batch = queue.create_sync_batch(limit=50)
    assert batch is not None
    assert batch.count == 2

    # 3. Send over wire to server sync endpoint
    response = client.post(
        "/api/v1/devices/sync",
        headers={"X-Device-Id": str(device_id)},
        json=batch.model_dump(mode="json"),
    )
    assert response.status_code == 200
    ack = SyncAck(**response.json())

    # 4. Acknowledge sync in offline queue
    acked_count = queue.acknowledge_batch(ack)
    assert acked_count == 2

    counts_after = queue.get_sync_counts()
    assert counts_after[SyncStatus.LOCALLY_SAVED.value] == 0
    assert counts_after[SyncStatus.SERVER_SYNCHRONIZED.value] == 2

    all_reports = queue.list_reports()
    assert all(r.sync_status == SyncStatus.SERVER_SYNCHRONIZED for r in all_reports)

    # 5. Verify PostgreSQL server state
    db_session.expire_all()
    pg_reports = db_session.query(ReportModel).filter_by(device_id=device_id).all()
    assert len(pg_reports) == 2
    cursor = db_session.query(SyncCursorModel).filter_by(device_id=device_id).first()
    assert cursor is not None
    assert cursor.last_sequence == 2
