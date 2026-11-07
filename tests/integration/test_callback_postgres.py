"""Integration tests for PostgresCallbackJobRepository and PostgreSQL-backed scheduler."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.database.models import CallbackJobModel, DisasterModel
from raahat.infrastructure.database.repositories.callback import PostgresCallbackJobRepository
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.telephony import (
    CallbackJob,
    CallbackScheduler,
    CallbackStatus,
    StubTelephonyProvider,
)

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine(TEST_DB_URL)
    return get_sync_sessionmaker(engine)


@pytest.fixture
def disaster_id(session_factory: sessionmaker[Session]) -> Generator[uuid.UUID, None, None]:
    with session_factory() as session:
        d_id = uuid.uuid4()
        disaster = DisasterModel(
            id=d_id,
            name="Callback Test Flood",
            disaster_type="flood",
            status="active",
        )
        session.add(disaster)
        session.commit()

    yield d_id

    with session_factory() as session:
        session.query(CallbackJobModel).filter_by(disaster_id=d_id).delete()
        session.query(DisasterModel).filter_by(id=d_id).delete()
        session.commit()


def test_postgres_callback_job_crud(
    session_factory: sessionmaker[Session],
    disaster_id: uuid.UUID,
) -> None:
    repo = PostgresCallbackJobRepository(session_factory)
    job_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    job = CallbackJob(
        id=job_id,
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
        status=CallbackStatus.SCHEDULED,
        scheduled_at=now,
        created_at=now,
        max_retries=3,
        retry_count=0,
        context={"caller_name": "Ramesh", "language": "hi"},
    )

    saved = repo.save(job)
    assert saved.id == job_id
    assert saved.phone_number == "+919876543210"
    assert saved.context == {"caller_name": "Ramesh", "language": "hi"}

    fetched = repo.get_by_id(job_id)
    assert fetched is not None
    assert fetched.id == job_id
    assert fetched.status == CallbackStatus.SCHEDULED

    # Claim due jobs
    claimed = repo.claim_due_jobs(now=now + timedelta(seconds=1), limit=10)
    assert len(claimed) >= 1
    claimed_ids = [j.id for j in claimed]
    assert job_id in claimed_ids

    # Update job
    updated_job = CallbackJob(
        id=job_id,
        disaster_id=disaster_id,
        phone_number="+919876543210",
        consent_given=True,
        status=CallbackStatus.COMPLETED,
        scheduled_at=now,
        created_at=now,
        max_retries=3,
        retry_count=0,
        completed_at=now,
        provider_call_id="call_test123",
        context=job.context,
    )
    res = repo.update(updated_job)
    assert res.status == CallbackStatus.COMPLETED
    assert res.provider_call_id == "call_test123"

    # Count by status
    counts = repo.count_by_status(disaster_id)
    assert counts[CallbackStatus.COMPLETED.value] >= 1

    # List by disaster
    listed = repo.list_by_disaster(disaster_id)
    assert any(j.id == job_id for j in listed)


@pytest.mark.asyncio
async def test_postgres_callback_scheduler_full_flow(
    session_factory: sessionmaker[Session],
    disaster_id: uuid.UUID,
) -> None:
    repo = PostgresCallbackJobRepository(session_factory)
    provider = StubTelephonyProvider()
    scheduler = CallbackScheduler(
        repository=repo,
        provider=provider,
        caller_id="+911077000000",
    )

    # 1. Schedule with consent
    job1 = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543219",
        consent_given=True,
        delay_seconds=0,
    )
    assert job1.status == CallbackStatus.SCHEDULED

    # 2. Schedule without consent
    job2 = scheduler.schedule_callback(
        disaster_id=disaster_id,
        phone_number="+919876543218",
        consent_given=False,
    )
    assert job2.status == CallbackStatus.CANCELLED_NO_CONSENT

    # Process due jobs
    processed = await scheduler.process_due_jobs(limit=10)
    # job1 should have been dialed and marked COMPLETED
    job1_processed = next((j for j in processed if j.id == job1.id), None)
    assert job1_processed is not None
    assert job1_processed.status == CallbackStatus.COMPLETED

    # Verify job2 was never even claimed as due because status is CANCELLED_NO_CONSENT
    assert not any(j.id == job2.id for j in processed)
    job2_db = repo.get_by_id(job2.id)
    assert job2_db is not None
    assert job2_db.status == CallbackStatus.CANCELLED_NO_CONSENT

