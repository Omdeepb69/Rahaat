"""Integration tests for PostgresEventOutbox and PostgresOutboxRepository.

Verifies transactional outbox event publishing, row-level leasing with
FOR UPDATE SKIP LOCKED, fencing token validation, and retry / dead-letter
settlement against PostgreSQL.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.database.models import OutboxEventModel
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.outbox import (
    DomainEvent,
    OutboxJob,
    OutboxJobStatus,
    PostgresEventOutbox,
    PostgresOutboxRepository,
)
from raahat.workers import OutboxWorker, OutboxWorkerConfig

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
        session.commit()
        yield session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_postgres_event_outbox_publish(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    publisher = PostgresEventOutbox()
    event = DomainEvent(
        event_type="raahat.report.received",
        aggregate_type="report",
        aggregate_id=uuid.uuid4(),
        payload={"caller": "+919999999999", "channel": "ivr"},
    )

    publisher.publish(event, db_session)
    db_session.commit()

    saved = db_session.get(OutboxEventModel, event.event_id)
    assert saved is not None
    assert saved.status == OutboxJobStatus.PENDING.value
    assert saved.event_type == "raahat.report.received"
    assert saved.aggregate_type == "report"
    assert saved.retry_count == 0


def test_postgres_outbox_repository_claim_batch(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    repo = PostgresOutboxRepository(session_factory)
    publisher = PostgresEventOutbox()

    event1 = DomainEvent(
        event_type="test.claim.1",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"idx": 1},
    )
    event2 = DomainEvent(
        event_type="test.claim.2",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"idx": 2},
    )
    publisher.publish(event1, db_session)
    publisher.publish(event2, db_session)
    db_session.commit()

    claims = repo.claim_pending_batch(batch_size=2, lease_duration=timedelta(minutes=1))
    assert len(claims) >= 2
    claimed_ids = {c.job.id for c in claims}
    assert event1.event_id in claimed_ids
    assert event2.event_id in claimed_ids

    # Verify rows in DB are marked CLAIMED and have tokens
    db_session.expire_all()
    r1 = db_session.get(OutboxEventModel, event1.event_id)
    assert r1 is not None
    assert r1.status == OutboxJobStatus.CLAIMED.value
    assert r1.lease_token is not None
    assert r1.lease_expires_at is not None


def test_postgres_outbox_repository_fencing_guard(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    repo = PostgresOutboxRepository(session_factory)
    publisher = PostgresEventOutbox()

    event = DomainEvent(
        event_type="test.fencing",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={},
    )
    publisher.publish(event, db_session)
    db_session.commit()

    claims = repo.claim_pending_batch(batch_size=10, lease_duration=timedelta(minutes=1))
    target_claim = next(c for c in claims if c.job.id == event.event_id)

    # Attempt to mark succeeded with wrong / stale lease token
    stale_token = uuid.uuid4()
    success = repo.mark_succeeded(event.event_id, stale_token, _utc_now())
    assert success is False

    # Verify row was NOT marked succeeded
    db_session.expire_all()
    saved = db_session.get(OutboxEventModel, event.event_id)
    assert saved is not None
    assert saved.status == OutboxJobStatus.CLAIMED.value

    # Now settle with the correct token
    success_legit = repo.mark_succeeded(event.event_id, target_claim.lease_token, _utc_now())
    assert success_legit is True

    db_session.expire_all()
    saved_after = db_session.get(OutboxEventModel, event.event_id)
    assert saved_after is not None
    assert saved_after.status == OutboxJobStatus.SUCCEEDED.value


def test_postgres_outbox_repository_retry_and_dead_letter(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    repo = PostgresOutboxRepository(session_factory)
    publisher = PostgresEventOutbox()

    event = DomainEvent(
        event_type="test.dead_letter",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={},
    )
    publisher.publish(event, db_session)
    db_session.commit()

    # Claim
    claims = repo.claim_pending_batch(batch_size=10, lease_duration=timedelta(minutes=1))
    claim = next(c for c in claims if c.job.id == event.event_id)

    # First failure: new_retry_count=1, max_retries=2 -> RETRYABLE_FAILURE
    repo.mark_failed(event.event_id, claim.lease_token, new_retry_count=1, max_retries=2)
    db_session.expire_all()
    r = db_session.get(OutboxEventModel, event.event_id)
    assert r is not None
    assert r.status == OutboxJobStatus.RETRYABLE_FAILURE.value
    assert r.retry_count == 1
    assert r.lease_token is None

    # Re-claim as retryable
    claims_retry = repo.claim_pending_batch(batch_size=10, lease_duration=timedelta(minutes=1))
    claim_retry = next(c for c in claims_retry if c.job.id == event.event_id)

    # Second failure: new_retry_count=2, max_retries=2 -> DEAD_LETTER
    repo.mark_failed(event.event_id, claim_retry.lease_token, new_retry_count=2, max_retries=2)
    db_session.expire_all()
    r_dead = db_session.get(OutboxEventModel, event.event_id)
    assert r_dead is not None
    assert r_dead.status == OutboxJobStatus.DEAD_LETTER.value
    assert r_dead.retry_count == 2


def test_outbox_worker_end_to_end_with_postgres(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    repo = PostgresOutboxRepository(session_factory)
    publisher = PostgresEventOutbox()

    event = DomainEvent(
        event_type="raahat.incident.triaged",
        aggregate_type="incident",
        aggregate_id=uuid.uuid4(),
        payload={"urgency": "high"},
    )
    publisher.publish(event, db_session)
    db_session.commit()

    processed: list[OutboxJob] = []

    def handler(job: OutboxJob) -> None:
        if job.id == event.event_id:
            processed.append(job)

    worker = OutboxWorker(
        repository=repo,
        handler=handler,
        config=OutboxWorkerConfig(batch_size=10),
    )

    worker.run_once()

    assert len(processed) == 1
    assert processed[0].id == event.event_id
    assert processed[0].payload == {"urgency": "high"}

    db_session.expire_all()
    saved = db_session.get(OutboxEventModel, event.event_id)
    assert saved is not None
    assert saved.status == OutboxJobStatus.SUCCEEDED.value
    assert saved.processed_at is not None
