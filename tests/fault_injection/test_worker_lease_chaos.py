"""Fault injection tests for worker crashes, expired lease recovery, and fencing token protection."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from raahat.infrastructure.outbox import ClaimResult, OutboxJob, OutboxJobStatus
from raahat.infrastructure.telephony import (
    CallbackJob,
    CallbackScheduler,
    CallbackStatus,
    StubTelephonyProvider,
)
from raahat.infrastructure.telephony.repository import CallbackJobRepository
from raahat.workers.callback_worker import CallbackWorker, CallbackWorkerConfig
from raahat.workers.runner import (
    OutboxWorker,
    OutboxWorkerConfig,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChaosRow:
    def __init__(
        self,
        id: uuid.UUID,
        event_type: str = "report.process",
        status: str = OutboxJobStatus.PENDING.value,
        retry_count: int = 0,
        lease_token: uuid.UUID | None = None,
        lease_expires_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.aggregate_type = "report"
        self.aggregate_id = uuid.uuid4()
        self.event_type = event_type
        self.payload: dict[str, Any] = {"raw_audio": "clip.wav"}
        self.status = status
        self.retry_count = retry_count
        self.lease_token = lease_token
        self.lease_expires_at = lease_expires_at
        self.processed_at: datetime | None = None


class ChaosOutboxRepository:
    """In-memory outbox repository supporting simulated crashes, clocks, and fencing."""

    def __init__(self, clock_fn: Any = _utc_now) -> None:
        self.rows: dict[uuid.UUID, ChaosRow] = {}
        self.clock = clock_fn

    def add_row(self, row: ChaosRow) -> None:
        self.rows[row.id] = row

    def claim_pending_batch(
        self,
        batch_size: int = 10,
        lease_duration: timedelta = timedelta(seconds=30),
    ) -> list[ClaimResult]:
        now = self.clock()
        claims: list[ClaimResult] = []

        for row in self.rows.values():
            if len(claims) >= batch_size:
                break

            # Claim eligible if PENDING or RETRYABLE_FAILURE, or lease expired
            is_pending = row.status in (
                OutboxJobStatus.PENDING.value,
                OutboxJobStatus.RETRYABLE_FAILURE.value,
            )
            is_stale_lease = (
                row.status == OutboxJobStatus.CLAIMED.value
                and row.lease_expires_at is not None
                and row.lease_expires_at <= now
            )

            if is_pending or is_stale_lease:
                token = uuid.uuid4()
                row.status = OutboxJobStatus.CLAIMED.value
                row.lease_token = token
                row.lease_expires_at = now + lease_duration

                job = OutboxJob(
                    id=row.id,
                    aggregate_type=row.aggregate_type,
                    aggregate_id=row.aggregate_id,
                    event_type=row.event_type,
                    payload=dict(row.payload),
                    retry_count=row.retry_count,
                    lease_token=token,
                )
                claims.append(ClaimResult(job=job, lease_token=token))

        return claims

    def mark_succeeded(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        processed_at: datetime,
    ) -> bool:
        row = self.rows.get(job_id)
        if not row:
            return False
        # Fencing token guard: reject if lease_token has been superseded
        if row.lease_token != lease_token:
            return False

        row.status = OutboxJobStatus.SUCCEEDED.value
        row.processed_at = processed_at
        row.lease_token = None
        row.lease_expires_at = None
        return True

    def mark_failed(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        new_retry_count: int,
        max_retries: int = 5,
    ) -> bool:
        row = self.rows.get(job_id)
        if not row:
            return False
        if row.lease_token != lease_token:
            return False

        row.retry_count = new_retry_count
        if new_retry_count >= max_retries:
            row.status = OutboxJobStatus.DEAD_LETTER.value
        else:
            row.status = OutboxJobStatus.RETRYABLE_FAILURE.value

        row.lease_token = None
        row.lease_expires_at = None
        return True


def test_worker_crash_and_expired_lease_automatic_recovery() -> None:
    """Scenario: Worker 1 claims a job, crashes mid-processing without settling.

    After lease expiration, Worker 2 must claim and complete the job.
    """
    current_time = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
    repo = ChaosOutboxRepository(clock_fn=lambda: current_time)

    job_id = uuid.uuid4()
    repo.add_row(ChaosRow(id=job_id))

    # Worker 1 claims the job
    worker1_cfg = OutboxWorkerConfig(lease_duration=timedelta(seconds=10))
    claims = repo.claim_pending_batch(batch_size=1, lease_duration=worker1_cfg.lease_duration)
    assert len(claims) == 1
    assert claims[0].job.id == job_id
    assert repo.rows[job_id].status == OutboxJobStatus.CLAIMED.value

    # Worker 1 CRASHES HERE (process abruptly killed; no settle called)

    # Clock advances past lease expiration (+15 seconds)
    current_time += timedelta(seconds=15)

    # Worker 2 starts up and polls
    processed_by_worker2: list[uuid.UUID] = []

    def worker2_handler(job: OutboxJob) -> None:
        processed_by_worker2.append(job.id)

    worker2 = OutboxWorker(
        repository=repo,  # type: ignore[arg-type]
        handler=worker2_handler,
        config=OutboxWorkerConfig(lease_duration=timedelta(seconds=10)),
    )
    count = worker2.run_once()

    assert count == 1
    assert processed_by_worker2 == [job_id]
    # Verify row reached SUCCEEDED under Worker 2
    assert repo.rows[job_id].status == OutboxJobStatus.SUCCEEDED.value


def test_fencing_token_rejects_zombie_worker() -> None:
    """Scenario: Worker 1 hangs past its lease. Worker 2 takes over and finishes.

    When Worker 1 unfreezes, its stale write must be rejected by the fencing guard.
    """
    current_time = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
    repo = ChaosOutboxRepository(clock_fn=lambda: current_time)

    job_id = uuid.uuid4()
    repo.add_row(ChaosRow(id=job_id))

    # Worker 1 claims job
    claims1 = repo.claim_pending_batch(batch_size=1, lease_duration=timedelta(seconds=5))
    claim1 = claims1[0]
    token1 = claim1.lease_token

    # Lease expires while Worker 1 is frozen
    current_time += timedelta(seconds=10)

    # Worker 2 claims the same job with a new fencing token
    claims2 = repo.claim_pending_batch(batch_size=1, lease_duration=timedelta(seconds=10))
    claim2 = claims2[0]
    token2 = claim2.lease_token
    assert token1 != token2

    # Worker 2 finishes and settles successfully
    success2 = repo.mark_succeeded(job_id, token2, processed_at=current_time)
    assert success2 is True
    assert repo.rows[job_id].status == OutboxJobStatus.SUCCEEDED.value

    # Zombie Worker 1 unfreezes and attempts to settle with its old token1
    success1 = repo.mark_succeeded(job_id, token1, processed_at=current_time)
    assert success1 is False, "Fencing token guard MUST reject stale write from zombie worker!"


def test_repeated_worker_crashes_dead_letter_without_loss() -> None:
    """Scenario: Poison-pill job crashes worker handler on every attempt.

    Must increment retry_count and safely reach DEAD_LETTER without dropping from table.
    """
    repo = ChaosOutboxRepository()
    job_id = uuid.uuid4()
    repo.add_row(ChaosRow(id=job_id))

    def crashing_handler(job: OutboxJob) -> None:
        raise RuntimeError("Speech recognizer model crashed: OOM segmentation fault")

    worker = OutboxWorker(
        repository=repo,  # type: ignore[arg-type]
        handler=crashing_handler,
        config=OutboxWorkerConfig(batch_size=1, max_retries=3),
    )

    # Attempt 1
    worker.run_once()
    assert repo.rows[job_id].status == OutboxJobStatus.RETRYABLE_FAILURE.value
    assert repo.rows[job_id].retry_count == 1

    # Attempt 2
    worker.run_once()
    assert repo.rows[job_id].status == OutboxJobStatus.RETRYABLE_FAILURE.value
    assert repo.rows[job_id].retry_count == 2

    # Attempt 3 -> Reaches max_retries (3)
    worker.run_once()
    assert repo.rows[job_id].status == OutboxJobStatus.DEAD_LETTER.value
    assert repo.rows[job_id].retry_count == 3
    # Report remains safely stored in table
    assert job_id in repo.rows


@pytest.mark.asyncio
async def test_telephony_gateway_crash_and_recovery() -> None:
    """Scenario: Telephony provider gateway crashes; worker retries and recovers.

    Guarantees no false success and zero infinite redial loops.
    """
    provider = StubTelephonyProvider(should_fail=True, failure_error="502 Bad Gateway from SIP trunk")

    class FakeCallbackRepo(CallbackJobRepository):
        def __init__(self) -> None:
            self.jobs: dict[uuid.UUID, CallbackJob] = {}

        def save(self, job: CallbackJob) -> CallbackJob:
            self.jobs[job.id] = job
            return job

        def get_by_id(self, job_id: uuid.UUID) -> CallbackJob | None:
            return self.jobs.get(job_id)

        def claim_due_jobs(self, now: datetime, limit: int = 10) -> list[CallbackJob]:
            due = [j for j in self.jobs.values() if j.status in (CallbackStatus.PENDING, CallbackStatus.SCHEDULED)]
            for j in due:
                self.jobs[j.id] = CallbackJob(
                    id=j.id,
                    disaster_id=j.disaster_id,
                    phone_number=j.phone_number,
                    consent_given=j.consent_given,
                    status=CallbackStatus.DIALING,
                    scheduled_at=j.scheduled_at,
                    created_at=j.created_at,
                    max_retries=j.max_retries,
                    retry_count=j.retry_count,
                    last_attempted_at=now,
                    context=j.context,
                )
            return due

        def update(self, job: CallbackJob) -> CallbackJob:
            self.jobs[job.id] = job
            return job

        def list_by_disaster(self, disaster_id: uuid.UUID, status: Any = None, limit: int = 50) -> list[CallbackJob]:
            return list(self.jobs.values())

        def count_by_status(self, disaster_id: uuid.UUID) -> dict[str, int]:
            return {}

    repo = FakeCallbackRepo()
    scheduler = CallbackScheduler(repository=repo, provider=provider, default_max_retries=3, base_backoff_seconds=5)
    worker = CallbackWorker(scheduler, CallbackWorkerConfig(batch_size=1))

    # Schedule callback
    disaster_id = uuid.uuid4()
    job = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
    )

    # 1. First run: provider gateway crashes
    processed_count = await worker.run_once()
    assert processed_count == 1
    saved_job = repo.get_by_id(job.id)
    assert saved_job is not None
    assert saved_job.status == CallbackStatus.SCHEDULED
    assert saved_job.retry_count == 1
    assert "502 Bad Gateway" in (saved_job.failure_reason or "")

    # 2. Provider recovers!
    provider.should_fail = False

    # Simulate due time reached
    saved_job = CallbackJob(
        id=saved_job.id,
        disaster_id=saved_job.disaster_id,
        phone_number=saved_job.phone_number,
        consent_given=saved_job.consent_given,
        status=CallbackStatus.SCHEDULED,
        scheduled_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        created_at=saved_job.created_at,
        max_retries=saved_job.max_retries,
        retry_count=saved_job.retry_count,
        context=saved_job.context,
    )
    repo.update(saved_job)

    # 3. Second run: dials successfully and marks COMPLETED
    await worker.run_once()
    final_job = repo.get_by_id(job.id)
    assert final_job is not None
    assert final_job.status == CallbackStatus.COMPLETED
    assert final_job.completed_at is not None
    assert final_job.provider_call_id is not None
