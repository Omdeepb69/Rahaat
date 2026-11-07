"""Audit event repository with cryptographic hash chaining."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session, sessionmaker

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
