"""Transactional outbox publisher protocol and PostgreSQL implementation.

The ``EventOutbox`` protocol defines the write side of the outbox: callers
invoke ``publish`` *inside the same database transaction* that mutates the
aggregate, so the event and the aggregate state are always durable together.

The ``PostgresEventOutbox`` implementation is intentionally thin — it writes
one row to ``outbox_events`` and nothing else.  The background worker in
``src/raahat/workers/runner.py`` handles relay, retries, and dead-lettering.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from ..database.models.outbox import OutboxEventModel
from .events import DomainEvent


class EventOutbox(Protocol):
    """Write side of the transactional outbox.

    Implementations must append the event atomically within ``session``'s
    active transaction.  Callers commit the transaction; this method must
    not commit or roll back independently.
    """

    def publish(self, event: DomainEvent, session: Session) -> None: ...


class PostgresEventOutbox:
    """Writes ``DomainEvent`` rows to ``outbox_events`` via SQLAlchemy.

    Call ``publish`` inside a ``Session`` that is already in a transaction.
    The caller owns the commit.
    """

    def publish(self, event: DomainEvent, session: Session) -> None:
        row = OutboxEventModel(
            id=event.event_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
            payload=event.payload,
            status="pending",
            retry_count=0,
        )
        session.add(row)

