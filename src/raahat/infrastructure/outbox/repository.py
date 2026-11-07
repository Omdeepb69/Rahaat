"""OutboxRepository protocol, job types, and PostgreSQL implementation.

The OutboxRepository protocol defines the database interface for the outbox
worker.  OutboxJob and ClaimResult are the value types that cross the boundary
between the repository and the worker loop.

Keeping these types here (not in workers/) avoids a circular dependency:
  workers.runner → infrastructure.outbox.repository  (one-way, correct)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, Sequence

from sqlalchemy import and_, or_, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from ..database.models.outbox import OutboxEventModel
from .events import OutboxJobStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Job value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxJob:
    """Snapshot of a claimed outbox row handed to a handler."""

    id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    retry_count: int
    lease_token: uuid.UUID


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of a single-row claim attempt."""

    job: OutboxJob
    lease_token: uuid.UUID


# ---------------------------------------------------------------------------
# Repository protocol
# ---------------------------------------------------------------------------


class OutboxRepository(Protocol):
    """Database interface for the outbox worker.

    All methods that mutate rows operate inside a short, auto-committed
    transaction.  The caller (OutboxWorker) owns transaction boundaries.
    """

    def claim_pending_batch(
        self,
        batch_size: int,
        lease_duration: timedelta,
    ) -> Sequence[ClaimResult]:
        """Atomically claim up to ``batch_size`` eligible rows.

        Eligible rows: status IN (PENDING, RETRYABLE_FAILURE) with
        lease_expires_at IS NULL or lease_expires_at < now().

        Each claimed row is updated: status=CLAIMED, fresh lease_token,
        lease_expires_at = now() + lease_duration.
        """
        ...

    def mark_succeeded(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        processed_at: datetime,
    ) -> bool:
        """Set status=SUCCEEDED on the row iff lease_token matches.

        Returns True if updated (token matched), False if lease was stolen.
        """
        ...

    def mark_failed(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        new_retry_count: int,
        max_retries: int,
    ) -> bool:
        """Increment retry_count and advance status.

        new_retry_count >= max_retries → DEAD_LETTER.
        Otherwise → RETRYABLE_FAILURE, lease cleared.

        Returns True if updated (token matched), False if lease was stolen.
        """
        ...


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------


class PostgresOutboxRepository:
    """Production ``OutboxRepository`` backed by PostgreSQL.

    Uses ``SELECT … FOR UPDATE SKIP LOCKED`` to claim rows without blocking
    sibling workers.  Each claim writes a fresh UUID fencing token and a
    deadline.  All writes happen inside short, explicitly managed transactions.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory

    def claim_pending_batch(
        self,
        batch_size: int,
        lease_duration: timedelta,
    ) -> Sequence[ClaimResult]:
        now = _utc_now()
        expires_at = now + lease_duration
        results: list[ClaimResult] = []

        with self._factory() as session:
            with session.begin():
                eligible_statuses = [
                    OutboxJobStatus.PENDING.value,
                    OutboxJobStatus.RETRYABLE_FAILURE.value,
                ]
                rows = (
                    session.query(OutboxEventModel)
                    .filter(
                        OutboxEventModel.status.in_(eligible_statuses),
                        or_(
                            OutboxEventModel.lease_expires_at.is_(None),
                            OutboxEventModel.lease_expires_at < now,
                        ),
                    )
                    .order_by(OutboxEventModel.created_at.asc())
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                    .all()
                )

                for row in rows:
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
        with self._factory() as session:
            with session.begin():
                result = session.execute(
                    update(OutboxEventModel)
                    .where(
                        and_(
                            OutboxEventModel.id == job_id,
                            OutboxEventModel.lease_token == lease_token,
                        )
                    )
                    .values(
                        status=OutboxJobStatus.SUCCEEDED.value,
                        processed_at=processed_at,
                    )
                )
                assert isinstance(result, CursorResult)
                return bool(result.rowcount == 1)

    def mark_failed(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        new_retry_count: int,
        max_retries: int,
    ) -> bool:
        new_status = (
            OutboxJobStatus.DEAD_LETTER.value
            if new_retry_count >= max_retries
            else OutboxJobStatus.RETRYABLE_FAILURE.value
        )
        with self._factory() as session:
            with session.begin():
                result = session.execute(
                    update(OutboxEventModel)
                    .where(
                        and_(
                            OutboxEventModel.id == job_id,
                            OutboxEventModel.lease_token == lease_token,
                        )
                    )
                    .values(
                        status=new_status,
                        retry_count=new_retry_count,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                assert isinstance(result, CursorResult)
                return bool(result.rowcount == 1)

