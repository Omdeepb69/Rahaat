"""Audit event repository with cryptographic hash chaining."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.audit import AuditEventModel


def compute_audit_hash(
    prev_hash: Optional[str],
    action: str,
    actor_id: Optional[uuid.UUID],
    entity_type: str,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
) -> str:
    """Compute SHA-256 tamper-evident hash chaining for an audit event."""
    serialized_payload = json.dumps(payload, sort_keys=True, default=str)
    content = (
        f"{prev_hash or ''}:{action}:{str(actor_id) if actor_id else ''}:"
        f"{entity_type}:{str(entity_id)}:{serialized_payload}"
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Every writer takes this transaction-scoped advisory lock before allocating a
# sequence number. Holding it until commit makes sequence order equal commit
# order, so a reader that has seen sequence N never misses a lower number
# committing later, and hash-chain predecessors are read consistently.
AUDIT_APPEND_LOCK_KEY = 0x52414148  # "RAAH"


def append_audit(
    session: Session,
    *,
    action: str,
    actor_id: Optional[uuid.UUID],
    entity_type: str,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
    disaster_id: Optional[uuid.UUID] = None,
    incident_id: Optional[uuid.UUID] = None,
) -> AuditEventModel:
    """Append a hash-chained audit record inside the caller's transaction.

    The record commits or rolls back with the change it describes. It is also
    the realtime event: an insert trigger notifies stream subscribers.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": AUDIT_APPEND_LOCK_KEY}
    )
    prev_hash = session.execute(
        select(AuditEventModel.hash)
        .where(
            AuditEventModel.entity_type == entity_type,
            AuditEventModel.entity_id == entity_id,
        )
        .order_by(AuditEventModel.seq.desc())
        .limit(1)
    ).scalar_one_or_none()
    if incident_id is None and entity_type == "incident":
        incident_id = entity_id
    event = AuditEventModel(
        id=uuid.uuid4(),
        action=action,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        disaster_id=disaster_id,
        incident_id=incident_id,
        prev_hash=prev_hash,
        hash=compute_audit_hash(
            prev_hash=prev_hash,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        ),
        payload=payload,
        created_at=utc_now(),
    )
    session.add(event)
    session.flush()
    return event


@runtime_checkable
class AuditRepository(Protocol):
    """Protocol for tamper-evident audit logging."""

    def record_event(
        self,
        action: str,
        actor_id: Optional[uuid.UUID],
        entity_type: str,
        entity_id: uuid.UUID,
        payload: dict[str, Any],
        session: Optional[Any] = None,
        disaster_id: Optional[uuid.UUID] = None,
        incident_id: Optional[uuid.UUID] = None,
    ) -> AuditEventModel: ...

    def get_latest_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Optional[AuditEventModel]: ...

    def get_event_by_id(
        self,
        event_id: uuid.UUID,
    ) -> Optional[AuditEventModel]: ...

    def get_entity_chain(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AuditEventModel]: ...

    def query_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEventModel]: ...

    def count_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> int: ...

    def list_distinct_entities(
        self,
    ) -> list[tuple[str, uuid.UUID]]: ...


class PostgresAuditRepository:
    """AuditRepository backed by PostgreSQL with cryptographic hash chaining."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_latest_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Optional[AuditEventModel]:
        """Fetch the most recent audit event for hash chaining."""
        with self._session_factory() as session:
            return (
                session.query(AuditEventModel)
                .filter_by(entity_type=entity_type, entity_id=entity_id)
                .order_by(AuditEventModel.seq.desc())
                .first()
            )

    def get_event_by_id(
        self,
        event_id: uuid.UUID,
    ) -> Optional[AuditEventModel]:
        """Fetch an audit event by its unique ID."""
        with self._session_factory() as session:
            return session.get(AuditEventModel, event_id)

    def get_entity_chain(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AuditEventModel]:
        """Fetch all events for a specific entity in chronological chain order."""
        with self._session_factory() as session:
            stmt = (
                select(AuditEventModel)
                .where(
                    AuditEventModel.entity_type == entity_type,
                    AuditEventModel.entity_id == entity_id,
                )
                .order_by(AuditEventModel.seq.asc())
            )
            return list(session.scalars(stmt).all())

    def query_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEventModel]:
        """Query audit records with optional filters, newest first."""
        with self._session_factory() as session:
            stmt = select(AuditEventModel)
            if entity_type is not None:
                stmt = stmt.where(AuditEventModel.entity_type == entity_type)
            if entity_id is not None:
                stmt = stmt.where(AuditEventModel.entity_id == entity_id)
            if action is not None:
                stmt = stmt.where(AuditEventModel.action == action)
            if actor_id is not None:
                stmt = stmt.where(AuditEventModel.actor_id == actor_id)

            stmt = stmt.order_by(AuditEventModel.seq.desc())
            stmt = stmt.limit(limit).offset(offset)
            return list(session.scalars(stmt).all())

    def count_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Count audit records matching the specified filters."""
        with self._session_factory() as session:
            stmt = select(func.count(AuditEventModel.id))
            if entity_type is not None:
                stmt = stmt.where(AuditEventModel.entity_type == entity_type)
            if entity_id is not None:
                stmt = stmt.where(AuditEventModel.entity_id == entity_id)
            if action is not None:
                stmt = stmt.where(AuditEventModel.action == action)
            if actor_id is not None:
                stmt = stmt.where(AuditEventModel.actor_id == actor_id)

            return session.scalar(stmt) or 0

    def list_distinct_entities(
        self,
    ) -> list[tuple[str, uuid.UUID]]:
        """Return list of distinct (entity_type, entity_id) pairs present in the audit log."""
        with self._session_factory() as session:
            stmt = (
                select(AuditEventModel.entity_type, AuditEventModel.entity_id)
                .distinct()
                .order_by(AuditEventModel.entity_type, AuditEventModel.entity_id)
            )
            return [(row[0], row[1]) for row in session.execute(stmt).all()]

    def record_event(
        self,
        action: str,
        actor_id: Optional[uuid.UUID],
        entity_type: str,
        entity_id: uuid.UUID,
        payload: dict[str, Any],
        session: Optional[Session] = None,
        disaster_id: Optional[uuid.UUID] = None,
        incident_id: Optional[uuid.UUID] = None,
    ) -> AuditEventModel:
        """Append an audit record.

        With ``session`` the record joins the caller's transaction, which is
        how application services use it. Without one it commits on its own.
        """
        if session is not None:
            return append_audit(
                session,
                action=action,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                disaster_id=disaster_id,
                incident_id=incident_id,
            )
        with self._session_factory() as own_session:
            event = append_audit(
                own_session,
                action=action,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
                disaster_id=disaster_id,
                incident_id=incident_id,
            )
            own_session.commit()
            own_session.refresh(event)
            return event


class InMemoryAuditRepository:
    """In-memory implementation of AuditRepository with hash chaining for unit tests."""

    def __init__(self) -> None:
        self.events: list[AuditEventModel] = []

    def get_latest_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Optional[AuditEventModel]:
        matching = [
            e for e in self.events
            if e.entity_type == entity_type and e.entity_id == entity_id
        ]
        return matching[-1] if matching else None

    def get_event_by_id(
        self,
        event_id: uuid.UUID,
    ) -> Optional[AuditEventModel]:
        for e in self.events:
            if e.id == event_id:
                return e
        return None

    def get_entity_chain(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AuditEventModel]:
        return [
            e for e in self.events
            if e.entity_type == entity_type and e.entity_id == entity_id
        ]

    def query_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEventModel]:
        filtered = self.events
        if entity_type is not None:
            filtered = [e for e in filtered if e.entity_type == entity_type]
        if entity_id is not None:
            filtered = [e for e in filtered if e.entity_id == entity_id]
        if action is not None:
            filtered = [e for e in filtered if e.action == action]
        if actor_id is not None:
            filtered = [e for e in filtered if e.actor_id == actor_id]

        filtered = sorted(filtered, key=lambda e: (e.created_at, str(e.id)), reverse=True)
        return filtered[offset : offset + limit]

    def count_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> int:
        filtered = self.events
        if entity_type is not None:
            filtered = [e for e in filtered if e.entity_type == entity_type]
        if entity_id is not None:
            filtered = [e for e in filtered if e.entity_id == entity_id]
        if action is not None:
            filtered = [e for e in filtered if e.action == action]
        if actor_id is not None:
            filtered = [e for e in filtered if e.actor_id == actor_id]

        return len(filtered)

    def list_distinct_entities(
        self,
    ) -> list[tuple[str, uuid.UUID]]:
        seen: set[tuple[str, uuid.UUID]] = set()
        result: list[tuple[str, uuid.UUID]] = []
        for e in self.events:
            pair = (e.entity_type, e.entity_id)
            if pair not in seen:
                seen.add(pair)
                result.append(pair)
        return sorted(result, key=lambda p: (p[0], str(p[1])))

    def record_event(
        self,
        action: str,
        actor_id: Optional[uuid.UUID],
        entity_type: str,
        entity_id: uuid.UUID,
        payload: dict[str, Any],
        session: Optional[Any] = None,
        disaster_id: Optional[uuid.UUID] = None,
        incident_id: Optional[uuid.UUID] = None,
    ) -> AuditEventModel:
        prev = self.get_latest_event(entity_type, entity_id)
        prev_hash = prev.hash if prev else None
        event_hash = compute_audit_hash(
            prev_hash=prev_hash,
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        model = AuditEventModel(
            id=uuid.uuid4(),
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            prev_hash=prev_hash,
            hash=event_hash,
            payload=payload,
            created_at=utc_now(),
        )
        self.events.append(model)
        return model
