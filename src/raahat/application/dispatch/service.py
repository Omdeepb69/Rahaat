"""Dispatch service: human-approved rescue assignment and operation lifecycle management."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.operations.operation import Assignment, OperationEvent
from raahat.domain.operations.repository import (
    AssignmentRepository,
    InMemoryAssignmentRepository,
    next_status_for_event,
    validate_event_transition,
)
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    InMemoryAuditRepository,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DispatchService:
    """Manages rescue assignment lifecycle with strict human-in-the-loop authorization.

    Every assignment is proposed by a dispatcher and every state transition requires
    an authenticated actor. No autonomous dispatch is permitted.
    """

    def __init__(
        self,
        assignment_repo: Optional[AssignmentRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._assignment_repo = assignment_repo or InMemoryAssignmentRepository()
        self._audit_repo = audit_repo or InMemoryAuditRepository()
        self._session_factory = session_factory

    def propose_assignment(
        self,
        incident_id: uuid.UUID,
        resource_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> tuple[Assignment, OperationEvent]:
        """Create a new PROPOSED assignment and record the PROPOSED operation event.

        Returns the saved (Assignment, OperationEvent) pair.
        Requires dispatcher_id — the zero autonomous dispatch rule is enforced at
        the API layer, but the service also validates it.
        """
        assignment = Assignment(
            incident_id=incident_id,
            resource_id=resource_id,
            assigned_by=dispatcher_id,
            status=AssignmentStatus.PROPOSED,
        )
        saved_assignment = self._assignment_repo.save(assignment)

        event = OperationEvent(
            assignment_id=saved_assignment.id,
            incident_id=incident_id,
            event_type=OperationEventType.PROPOSED,
            actor_id=dispatcher_id,
            notes=notes,
            payload={
                "resource_id": str(resource_id),
                "assigned_by": str(dispatcher_id),
            },
        )
        saved_event = self._assignment_repo.save_event(event)

        self._audit_repo.record_event(
            action="assignment.proposed",
            actor_id=dispatcher_id,
            entity_type="assignment",
            entity_id=saved_assignment.id,
            payload={
                "incident_id": str(incident_id),
                "resource_id": str(resource_id),
                "notes": notes,
            },
        )

        logger.info(
            "Assignment proposed: assignment_id=%s incident_id=%s resource_id=%s dispatcher=%s",
            saved_assignment.id,
            incident_id,
            resource_id,
            dispatcher_id,
        )
        return saved_assignment, saved_event

    def record_event(
        self,
        assignment_id: uuid.UUID,
        event_type: OperationEventType,
        actor_id: uuid.UUID,
        notes: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> tuple[Assignment, OperationEvent]:
        """Apply a lifecycle event to an existing assignment, enforcing valid transitions.

        Returns the updated (Assignment, OperationEvent) pair.
        Raises ValueError if the assignment does not exist or the transition is invalid.
        """
        assignment = self._assignment_repo.get_by_id(assignment_id)
        if assignment is None:
            raise ValueError(f"Assignment {assignment_id} not found")

        validate_event_transition(assignment.status, event_type)

        new_status = next_status_for_event(event_type)
        approved_at: Optional[datetime] = None
        if event_type == OperationEventType.APPROVED:
            approved_at = _utc_now()

        event = OperationEvent(
            assignment_id=assignment_id,
            incident_id=assignment.incident_id,
            event_type=event_type,
            actor_id=actor_id,
            notes=notes,
            payload=payload or {},
        )
        saved_event = self._assignment_repo.save_event(event)

        updated_assignment = self._assignment_repo.update_status(
            assignment_id=assignment_id,
            status=new_status,
            approved_at=approved_at,
        )
        if updated_assignment is None:
            raise ValueError(f"Assignment {assignment_id} disappeared during update")

        self._audit_repo.record_event(
            action=f"assignment.{event_type.value}",
            actor_id=actor_id,
            entity_type="assignment",
            entity_id=assignment_id,
            payload={
                "incident_id": str(assignment.incident_id),
                "event_type": event_type.value,
                "previous_status": assignment.status.value,
                "new_status": new_status.value,
                "notes": notes,
            },
        )

        logger.info(
            "Assignment event recorded: assignment_id=%s event=%s %s->%s actor=%s",
            assignment_id,
            event_type.value,
            assignment.status.value,
            new_status.value,
            actor_id,
        )
        return updated_assignment, saved_event

    def get_assignment(self, assignment_id: uuid.UUID) -> Optional[Assignment]:
        """Return the assignment for assignment_id, or None if not found."""
        return self._assignment_repo.get_by_id(assignment_id)

    def list_assignments(self, incident_id: uuid.UUID) -> list[Assignment]:
        """Return all assignments for the given incident, newest first."""
        return self._assignment_repo.list_by_incident(incident_id)

    def list_events(self, assignment_id: uuid.UUID) -> list[OperationEvent]:
        """Return all operation events for an assignment, oldest first."""
        return self._assignment_repo.list_events(assignment_id)

