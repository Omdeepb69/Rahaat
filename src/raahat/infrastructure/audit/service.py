"""Audit service managing event recording, querying, and cryptographic verification."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.audit.models import (
    ChainVerificationResult,
    GlobalVerificationResult,
)
from raahat.infrastructure.audit.verifier import AuditVerifier
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    InMemoryAuditRepository,
)

logger = logging.getLogger(__name__)


class AuditService:
    """Service providing append-only audit recording, inspection, and tamper verification."""

    def __init__(
        self,
        audit_repo: Optional[AuditRepository] = None,
        verifier: Optional[AuditVerifier] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._audit_repo = audit_repo or InMemoryAuditRepository()
        self._verifier = verifier or AuditVerifier()
        self._session_factory = session_factory

    def record_event(
        self,
        action: str,
        actor_id: Optional[uuid.UUID],
        entity_type: str,
        entity_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> AuditEventModel:
        """Append an immutable, cryptographic-hash-chained audit event."""
        return self._audit_repo.record_event(
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )

    def get_event(self, event_id: uuid.UUID) -> Optional[AuditEventModel]:
        """Fetch a single audit event by ID."""
        return self._audit_repo.get_event_by_id(event_id)

    def get_entity_chain(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> list[AuditEventModel]:
        """Fetch all audit events for a specific entity in chronological order."""
        return self._audit_repo.get_entity_chain(entity_type, entity_id)

    def query_events(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        actor_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventModel], int]:
        """Query audit events with pagination and filtering; returns (items, total_count)."""
        items = self._audit_repo.query_events(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
            limit=limit,
            offset=offset,
        )
        total = self._audit_repo.count_events(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_id,
        )
        return items, total

    def verify_entity_chain(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> ChainVerificationResult:
        """Verify cryptographic integrity of the event chain for a specific entity."""
        events = self._audit_repo.get_entity_chain(entity_type, entity_id)
        return self._verifier.verify_entity_chain(entity_type, entity_id, events)

    def verify_all_chains(self) -> GlobalVerificationResult:
        """Inspect and verify all entity chains in the audit repository."""
        return self._verifier.verify_all_chains(self._audit_repo)

