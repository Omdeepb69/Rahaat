"""Unit tests for outbound callback scheduler and telephony state machine."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from raahat.infrastructure.database.repositories.callback import InMemoryCallbackJobRepository
from raahat.infrastructure.telephony import (
    CallbackJob,
    CallbackScheduler,
    CallbackStatus,
    StubTelephonyProvider,
)
from raahat.workers.callback_worker import CallbackWorker, CallbackWorkerConfig


@pytest.fixture
def callback_repo() -> InMemoryCallbackJobRepository:
    return InMemoryCallbackJobRepository()


@pytest.fixture
def telephony_provider() -> StubTelephonyProvider:
    return StubTelephonyProvider()


@pytest.fixture
def scheduler(
    callback_repo: InMemoryCallbackJobRepository,
    telephony_provider: StubTelephonyProvider,
) -> CallbackScheduler:
    return CallbackScheduler(
        repository=callback_repo,
        provider=telephony_provider,
        caller_id="+911077000000",
        base_backoff_seconds=10,
        default_max_retries=3,
    )


def test_schedule_callback_without_consent_immediately_cancels(
    scheduler: CallbackScheduler,
    telephony_provider: StubTelephonyProvider,
) -> None:
    disaster_id = uuid.uuid4()
    job = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=False,
    )

    assert job.status == CallbackStatus.CANCELLED_NO_CONSENT
    assert job.consent_given is False
    assert job.failure_reason == "Caller consent was not provided"
    assert len(telephony_provider.dial_history) == 0


def test_schedule_callback_with_consent_schedules_job(
    scheduler: CallbackScheduler,
    callback_repo: InMemoryCallbackJobRepository,
) -> None:
    disaster_id = uuid.uuid4()
    job = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
        delay_seconds=60,
    )

    assert job.status == CallbackStatus.SCHEDULED
    assert job.consent_given is True
    assert job.retry_count == 0
    saved = callback_repo.get_by_id(job.id)
    assert saved is not None
    assert saved.id == job.id


@pytest.mark.asyncio
async def test_process_job_successful_dial(
    scheduler: CallbackScheduler,
    telephony_provider: StubTelephonyProvider,
) -> None:
    disaster_id = uuid.uuid4()
    job = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
    )

    processed = await scheduler.process_single_job(job)

    assert processed.status == CallbackStatus.COMPLETED
    assert processed.completed_at is not None
    assert processed.provider_call_id is not None
    assert len(telephony_provider.dial_history) == 1
    assert telephony_provider.dial_history[0]["phone_number"] == "+919876543210"


@pytest.mark.asyncio
async def test_process_job_retries_on_dial_failure_with_backoff(
    scheduler: CallbackScheduler,
    telephony_provider: StubTelephonyProvider,
) -> None:
    telephony_provider.should_fail = True
    telephony_provider.failure_error = "Subscriber line busy"

    disaster_id = uuid.uuid4()
    now = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)
    job = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
    )

    # First failure -> retry_count = 1, backoff = 10 * 2^0 = 10s
    res1 = await scheduler.process_single_job(job, now=now)
    assert res1.status == CallbackStatus.SCHEDULED
    assert res1.retry_count == 1
    assert res1.scheduled_at == datetime(2026, 11, 7, 10, 0, 10, tzinfo=timezone.utc)
    assert "busy" in (res1.failure_reason or "")

    # Second failure -> retry_count = 2, backoff = 10 * 2^1 = 20s
    res2 = await scheduler.process_single_job(res1, now=datetime(2026, 11, 7, 10, 0, 10, tzinfo=timezone.utc))
    assert res2.status == CallbackStatus.SCHEDULED
    assert res2.retry_count == 2
    assert res2.scheduled_at == datetime(2026, 11, 7, 10, 0, 30, tzinfo=timezone.utc)

    # Third failure -> retry_count = 3 >= max_retries (3) -> EXHAUSTED!
    res3 = await scheduler.process_single_job(res2, now=datetime(2026, 11, 7, 10, 0, 30, tzinfo=timezone.utc))
    assert res3.status == CallbackStatus.EXHAUSTED
    assert res3.retry_count == 3
    assert res3.completed_at is not None


@pytest.mark.asyncio
async def test_no_infinite_redial_loop_when_exhausted(
    scheduler: CallbackScheduler,
    telephony_provider: StubTelephonyProvider,
) -> None:
    # Create an already-exhausted job
    job = CallbackJob(
        id=uuid.uuid4(),
        disaster_id=uuid.uuid4(),
        phone_number="+919876543210",
        consent_given=True,
        status=CallbackStatus.DIALING,
        scheduled_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        max_retries=3,
        retry_count=3,
    )
    scheduler.repository.save(job)

    result = await scheduler.process_single_job(job)

    assert result.status == CallbackStatus.EXHAUSTED
    # Assert zero dials were made
    assert len(telephony_provider.dial_history) == 0


@pytest.mark.asyncio
async def test_callback_worker_run_once(
    scheduler: CallbackScheduler,
    callback_repo: InMemoryCallbackJobRepository,
) -> None:
    disaster_id = uuid.uuid4()
    scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
    )
    scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543211",
        consent_given=True,
    )

    worker = CallbackWorker(scheduler, CallbackWorkerConfig(batch_size=5))
    processed = await worker.run_once()

    assert processed == 2
    jobs = callback_repo.list_by_disaster(disaster_id)
    assert all(j.status == CallbackStatus.COMPLETED for j in jobs)


@pytest.mark.asyncio
async def test_callback_worker_loop_stops_on_event(
    scheduler: CallbackScheduler,
) -> None:
    worker = CallbackWorker(scheduler, CallbackWorkerConfig(poll_interval_s=0.01))
    stop_event = asyncio.Event()

    task = asyncio.create_task(worker.run(stop_event))
    await asyncio.sleep(0.05)
    stop_event.set()
    await task
    assert task.done()
