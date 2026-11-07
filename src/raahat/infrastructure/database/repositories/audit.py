"""Audit event repository with cryptographic hash chaining."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy import func, select
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
                .order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc())
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
                .order_by(AuditEventModel.created_at.asc(), AuditEventModel.id.asc())
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

            stmt = stmt.order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc())
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
    ) -> AuditEventModel:
        """Create and persist a tamper-evident audit record."""
        with self._session_factory() as session:
            prev = (
                session.query(AuditEventModel)
                .filter_by(entity_type=entity_type, entity_id=entity_id)
                .order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc())
                .first()
            )
            prev_hash = prev.hash if prev else None
            event_hash = compute_audit_hash(
                prev_hash=prev_hash,
                action=action,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )

            audit_event = AuditEventModel(
                id=uuid.uuid4(),
                action=action,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                prev_hash=prev_hash,
                hash=event_hash,
                payload=payload,
            )
            session.add(audit_event)
            session.commit()
            session.refresh(audit_event)
            return audit_event


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
