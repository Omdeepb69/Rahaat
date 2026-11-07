"""Unit tests for OfflineSyncQueue and offline synchronization lifecycle."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from field_app import (
    DatabaseManager,
    OfflineReportDraft,
    OfflineSyncQueue,
    SyncAck,
    SyncStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_enqueue_report_assigns_monotonic_sequence() -> None:
    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db, device_name="Volunteer-Phone-1")

    assert queue.get_current_sequence() == 0

    reports = []
    for i in range(5):
        draft = OfflineReportDraft(
            disaster_id=disaster_id,
            raw_payload={"people_count": i + 1, "needs": ["water"]},
            source_identity="Volunteer John",
        )
        report = queue.enqueue_report(draft)
        reports.append(report)

    # Sequences must be strictly monotonic: 1, 2, 3, 4, 5
    sequences = [r.sequence for r in reports]
    assert sequences == [1, 2, 3, 4, 5]

    for i, r in enumerate(reports, start=1):
        assert r.device_id == device_id
        assert r.idempotency_key == f"volunteer:{device_id}:{i}"
        assert r.sync_status == SyncStatus.LOCALLY_SAVED
        assert r.raw_payload["people_count"] == i

    assert queue.get_current_sequence() == 5


def test_create_sync_batch_status_transitions() -> None:
    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db)

    for i in range(3):
        queue.enqueue_report(
            OfflineReportDraft(
                disaster_id=disaster_id,
                raw_payload={"item": i},
            )
        )

    # Claim batch of size 2
    batch = queue.create_sync_batch(limit=2)
    assert batch is not None
    assert batch.device_id == device_id
    assert batch.count == 2
    assert batch.from_sequence == 1
    assert batch.to_sequence == 2

    # Check database status transitions
    reports = queue.list_reports()
    assert len(reports) == 3
    assert reports[0].sync_status == SyncStatus.SYNCING
    assert reports[0].batch_id == batch.batch_id
    assert reports[1].sync_status == SyncStatus.SYNCING
    assert reports[1].batch_id == batch.batch_id
    assert reports[2].sync_status == SyncStatus.LOCALLY_SAVED
    assert reports[2].batch_id is None

    counts = queue.get_sync_counts()
    assert counts[SyncStatus.SYNCING.value] == 2
    assert counts[SyncStatus.LOCALLY_SAVED.value] == 1


def test_acknowledge_batch_marks_server_synchronized() -> None:
    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db)

    for i in range(3):
        queue.enqueue_report(
            OfflineReportDraft(
                disaster_id=disaster_id,
                raw_payload={"item": i},
            )
        )

    batch = queue.create_sync_batch(limit=2)
    assert batch is not None

    synced_time = _utc_now()
    ack = SyncAck(
        device_id=device_id,
        batch_id=batch.batch_id,
        server_synced_at=synced_time,
        acknowledged_sequence=2,
        accepted_count=2,
    )
    acked_count = queue.acknowledge_batch(ack)
    assert acked_count == 2

    reports = queue.list_reports()
    assert reports[0].sync_status == SyncStatus.SERVER_SYNCHRONIZED
    assert reports[0].synced_at is not None
    assert reports[1].sync_status == SyncStatus.SERVER_SYNCHRONIZED

    # Next sync batch should NOT include already synchronized reports!
    next_batch = queue.create_sync_batch(limit=10)
    assert next_batch is not None
    assert next_batch.count == 1
    assert next_batch.items[0].sequence == 3


def test_fail_batch_resets_to_failed_for_retry() -> None:
    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db)

    queue.enqueue_report(
        OfflineReportDraft(
            disaster_id=disaster_id,
            raw_payload={"item": 1},
        )
    )

    batch = queue.create_sync_batch(limit=10)
    assert batch is not None

    # Simulate network failure
    failed_count = queue.fail_batch(batch.batch_id, error_message="HTTP 503 Service Unavailable")
    assert failed_count == 1

    report = queue.get_report(batch.items[0].event_id)
    assert report is not None
    assert report.sync_status == SyncStatus.FAILED
    assert report.error_message == "HTTP 503 Service Unavailable"

    # Retry should pick up the failed report again
    retry_batch = queue.create_sync_batch(limit=10)
    assert retry_batch is not None
    assert retry_batch.count == 1
    assert retry_batch.items[0].event_id == report.id


def test_empty_queue_returns_none_batch() -> None:
    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db)

    assert queue.create_sync_batch() is None
    counts = queue.get_sync_counts()
    assert all(c == 0 for c in counts.values())



def test_concurrent_enqueue_maintains_monotonic_sequence() -> None:
    import concurrent.futures

    db = DatabaseManager(":memory:")
    device_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    queue = OfflineSyncQueue(device_id=device_id, db=db)

    def _worker(worker_id: int) -> int:
        draft = OfflineReportDraft(
            disaster_id=disaster_id,
            raw_payload={"worker": worker_id},
        )
        report = queue.enqueue_report(draft)
        return report.sequence

    # 20 concurrent workers drafting reports simultaneously
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_worker, i) for i in range(20)]
        results = [f.result() for f in futures]

    # Sequences must be strictly 1..20 with no duplicates or gaps
    assert sorted(results) == list(range(1, 21))
    assert queue.get_current_sequence() == 20
