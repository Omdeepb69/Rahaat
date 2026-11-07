"""Unit tests for the OutboxWorker, leasing, fencing, and dead-letter logic.

These tests use a pure-Python FakeOutboxRepository to test worker semantics
without any dependency on a running database.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from unittest.mock import MagicMock

from raahat.infrastructure.database.models.outbox import OutboxEventModel
from raahat.infrastructure.outbox import (
    ClaimResult,
    DomainEvent,
    OutboxJob,
    OutboxJobStatus,
    PostgresEventOutbox,
)
from raahat.workers.runner import (
    OutboxWorker,
    OutboxWorkerConfig,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FakeRow:
    id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    status: str
    retry_count: int
    lease_token: uuid.UUID | None
    lease_expires_at: datetime | None
    processed_at: datetime | None
    created_at: datetime


class FakeOutboxRepository:
    """In-memory outbox repository for deterministic unit testing."""

    def __init__(self, rows: list[FakeRow] | None = None) -> None:
        self.rows: dict[uuid.UUID, FakeRow] = {r.id: r for r in (rows or [])}

    def add_row(
        self,
        *,
        aggregate_type: str = "report",
        aggregate_id: uuid.UUID | None = None,
        event_type: str = "report.received",
        payload: dict[str, Any] | None = None,
        status: str = OutboxJobStatus.PENDING.value,
        retry_count: int = 0,
        lease_token: uuid.UUID | None = None,
        lease_expires_at: datetime | None = None,
        created_at: datetime | None = None,
    ) -> FakeRow:
        row_id = uuid.uuid4()
        row = FakeRow(
            id=row_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id or uuid.uuid4(),
            event_type=event_type,
            payload=payload if payload is not None else {"key": "value"},
            status=status,
            retry_count=retry_count,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            processed_at=None,
            created_at=created_at or _utc_now(),
        )
        self.rows[row_id] = row
        return row

    def claim_pending_batch(
        self,
        batch_size: int,
        lease_duration: timedelta,
    ) -> Sequence[ClaimResult]:
        now = _utc_now()
        expires_at = now + lease_duration

        eligible: list[FakeRow] = []
        for r in sorted(self.rows.values(), key=lambda x: x.created_at):
            if r.status in (
                OutboxJobStatus.PENDING.value,
                OutboxJobStatus.RETRYABLE_FAILURE.value,
            ) or (
                r.status == OutboxJobStatus.CLAIMED.value
                and r.lease_expires_at is not None
                and r.lease_expires_at < now
            ):
                if r.lease_expires_at is None or r.lease_expires_at < now:
                    eligible.append(r)

        claimed = eligible[:batch_size]
        results: list[ClaimResult] = []
        for row in claimed:
            token = uuid.uuid4()
            row.status = OutboxJobStatus.CLAIMED.value
            row.lease_token = token
            row.lease_expires_at = expires_at
            results.append(
                ClaimResult(
                    job=OutboxJob(
                        id=row.id,
                        aggregate_type=row.aggregate_type,
                        aggregate_id=row.aggregate_id,
                        event_type=row.event_type,
                        payload=dict(row.payload),
                        retry_count=row.retry_count,
                        lease_token=token,
                    ),
                    lease_token=token,
                )
            )
        return results

    def mark_succeeded(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        processed_at: datetime,
    ) -> bool:
        row = self.rows.get(job_id)
        if row is None or row.lease_token != lease_token:
            return False
        row.status = OutboxJobStatus.SUCCEEDED.value
        row.processed_at = processed_at
        return True

    def mark_failed(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        new_retry_count: int,
        max_retries: int,
    ) -> bool:
        row = self.rows.get(job_id)
        if row is None or row.lease_token != lease_token:
            return False

        if new_retry_count >= max_retries:
            row.status = OutboxJobStatus.DEAD_LETTER.value
        else:
            row.status = OutboxJobStatus.RETRYABLE_FAILURE.value

        row.retry_count = new_retry_count
        row.lease_token = None
        row.lease_expires_at = None
        return True


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------


class TestOutboxWorkerLeasingAndFencing:
    def test_claim_and_process_success(self) -> None:
        repo = FakeOutboxRepository()
        row = repo.add_row(payload={"test": "data"})

        processed_jobs: list[OutboxJob] = []

        def handler(job: OutboxJob) -> None:
            processed_jobs.append(job)

        worker = OutboxWorker(
            repository=repo,
            handler=handler,
            config=OutboxWorkerConfig(batch_size=5),
        )

        count = worker.run_once()

        assert count == 1
        assert len(processed_jobs) == 1
        assert processed_jobs[0].id == row.id
        assert processed_jobs[0].payload == {"test": "data"}

        updated_row = repo.rows[row.id]
        assert updated_row.status == OutboxJobStatus.SUCCEEDED.value
        assert updated_row.processed_at is not None

    def test_batch_size_is_respected(self) -> None:
        repo = FakeOutboxRepository()
        for _ in range(5):
            repo.add_row()

        handled_count = 0

        def handler(job: OutboxJob) -> None:
            nonlocal handled_count
            handled_count += 1

        worker = OutboxWorker(
            repository=repo,
            handler=handler,
            config=OutboxWorkerConfig(batch_size=2),
        )

        batch_1_count = worker.run_once()
        assert batch_1_count == 2
        assert handled_count == 2

        # 3 rows still pending
        pending_count = sum(
            1 for r in repo.rows.values() if r.status == OutboxJobStatus.PENDING.value
        )
        assert pending_count == 3

    def test_fencing_token_rejects_stale_success(self) -> None:
        repo = FakeOutboxRepository()
        row = repo.add_row()

        def handler_with_lease_steal(job: OutboxJob) -> None:
            # Simulate a lease theft while handler was busy:
            # Another process stole the lease and set a new lease_token.
            new_thief_token = uuid.uuid4()
            repo.rows[job.id].lease_token = new_thief_token

        worker = OutboxWorker(
            repository=repo,
            handler=handler_with_lease_steal,
            config=OutboxWorkerConfig(),
        )

        worker.run_once()

        # Row must not be marked succeeded because fencing token check failed
        updated_row = repo.rows[row.id]
        assert updated_row.status != OutboxJobStatus.SUCCEEDED.value
        assert updated_row.processed_at is None

    def test_fencing_token_rejects_stale_failure(self) -> None:
        repo = FakeOutboxRepository()
        row = repo.add_row()

        def handler_fail_with_stolen_lease(job: OutboxJob) -> None:
            # Simulate lease steal
            repo.rows[job.id].lease_token = uuid.uuid4()
            raise RuntimeError("Task failed after losing lease")

        worker = OutboxWorker(
            repository=repo,
            handler=handler_fail_with_stolen_lease,
            config=OutboxWorkerConfig(),
        )

        worker.run_once()

        # Row should not have its retry count incremented by this worker
        updated_row = repo.rows[row.id]
        assert updated_row.status != OutboxJobStatus.RETRYABLE_FAILURE.value
        assert updated_row.retry_count == 0

    def test_retryable_failure_advances_status_and_clears_lease(self) -> None:
        repo = FakeOutboxRepository()
        row = repo.add_row()

        def failing_handler(job: OutboxJob) -> None:
            raise ConnectionError("Temporary upstream outage")

        worker = OutboxWorker(
            repository=repo,
            handler=failing_handler,
            config=OutboxWorkerConfig(max_retries=3),
        )

        worker.run_once()

        updated_row = repo.rows[row.id]
        assert updated_row.status == OutboxJobStatus.RETRYABLE_FAILURE.value
        assert updated_row.retry_count == 1
        assert updated_row.lease_token is None
        assert updated_row.lease_expires_at is None

    def test_dead_letter_promotion_when_max_retries_exceeded(self) -> None:
        repo = FakeOutboxRepository()
        # Row has already failed 2 times; max_retries is 3
        row = repo.add_row(retry_count=2)

        def failing_handler(job: OutboxJob) -> None:
            raise ValueError("Permanent malformed payload error")

        worker = OutboxWorker(
            repository=repo,
            handler=failing_handler,
            config=OutboxWorkerConfig(max_retries=3),
        )

        worker.run_once()

        updated_row = repo.rows[row.id]
        assert updated_row.status == OutboxJobStatus.DEAD_LETTER.value
        assert updated_row.retry_count == 3
        assert updated_row.lease_token is None

        # Confirm DEAD_LETTER is not reclaimed in subsequent run
        count = worker.run_once()
        assert count == 0

    def test_idempotent_lease_recovery_for_expired_lease(self) -> None:
        repo = FakeOutboxRepository()
        old_token = uuid.uuid4()
        # Stale row whose lease expired 5 minutes ago
        past_time = _utc_now() - timedelta(minutes=5)
        row = repo.add_row(
            status=OutboxJobStatus.CLAIMED.value,
            lease_token=old_token,
            lease_expires_at=past_time,
        )

        processed_ids: list[uuid.UUID] = []

        def handler(job: OutboxJob) -> None:
            processed_ids.append(job.id)

        worker = OutboxWorker(
            repository=repo,
            handler=handler,
            config=OutboxWorkerConfig(),
        )

        count = worker.run_once()
        assert count == 1
        assert processed_ids == [row.id]

        updated_row = repo.rows[row.id]
        assert updated_row.status == OutboxJobStatus.SUCCEEDED.value
        assert updated_row.lease_token != old_token

    def test_idempotent_lease_recovery_for_retryable_failure(self) -> None:
        repo = FakeOutboxRepository()
        row = repo.add_row(
            status=OutboxJobStatus.RETRYABLE_FAILURE.value,
            retry_count=1,
            lease_token=None,
            lease_expires_at=None,
        )

        processed_ids: list[uuid.UUID] = []

        def handler(job: OutboxJob) -> None:
            processed_ids.append(job.id)

        worker = OutboxWorker(
            repository=repo,
            handler=handler,
            config=OutboxWorkerConfig(),
        )

        count = worker.run_once()
        assert count == 1
        assert processed_ids == [row.id]

        updated_row = repo.rows[row.id]
        assert updated_row.status == OutboxJobStatus.SUCCEEDED.value

    def test_empty_batch_returns_zero(self) -> None:
        repo = FakeOutboxRepository()
        worker = OutboxWorker(
            repository=repo,
            handler=lambda j: None,
            config=OutboxWorkerConfig(),
        )
        assert worker.run_once() == 0


class TestPostgresEventOutboxUnit:
    def test_publish_adds_model_to_session(self) -> None:
        publisher = PostgresEventOutbox()
        mock_session = MagicMock()

        event = DomainEvent(
            event_type="incident.created",
            aggregate_type="incident",
            aggregate_id=uuid.uuid4(),
            payload={"priority": "urgent"},
        )

        publisher.publish(event, mock_session)

        mock_session.add.assert_called_once()
        added_arg = mock_session.add.call_args[0][0]
        assert isinstance(added_arg, OutboxEventModel)
        assert added_arg.id == event.event_id
        assert added_arg.event_type == "incident.created"
        assert added_arg.aggregate_type == "incident"
        assert added_arg.aggregate_id == event.aggregate_id
        assert added_arg.payload == {"priority": "urgent"}
        assert added_arg.status == "pending"
        assert added_arg.retry_count == 0
