"""Domain protocols for assignment and operation event persistence."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from raahat.domain.operations.operation import Assignment, OperationEvent
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType

# Valid state transitions from a given AssignmentStatus event perspective.
# The OperationEventType drives the AssignmentStatus transitions.
_EVENT_TRANSITIONS: dict[OperationEventType, tuple[set[AssignmentStatus], AssignmentStatus]] = {
    OperationEventType.PROPOSED: (
        set(),  # initial; no prior status required
        AssignmentStatus.PROPOSED,
    ),
    OperationEventType.APPROVED: (
        {AssignmentStatus.PROPOSED},
        AssignmentStatus.APPROVED,
    ),
    OperationEventType.ACKNOWLEDGED: (
        {AssignmentStatus.APPROVED},
        AssignmentStatus.APPROVED,  # status stays APPROVED; acknowledged is an event-only milestone
    ),
    OperationEventType.EN_ROUTE: (
        {AssignmentStatus.APPROVED},
        AssignmentStatus.APPROVED,
    ),
    OperationEventType.ON_SCENE: (
        {AssignmentStatus.APPROVED},
        AssignmentStatus.APPROVED,
    ),
    OperationEventType.RESCUED: (
        {AssignmentStatus.APPROVED},
        AssignmentStatus.COMPLETED,
    ),
    OperationEventType.CLOSED: (
        {AssignmentStatus.PROPOSED, AssignmentStatus.APPROVED, AssignmentStatus.COMPLETED},
        AssignmentStatus.COMPLETED,
    ),
}


def validate_event_transition(
    current_status: AssignmentStatus,
    event_type: OperationEventType,
) -> None:
    """Raise ValueError if event_type is not a valid transition from current_status.

    PROPOSED is special: it is the initial event and must only be used to create
    new assignments (no prior status to validate against).
    """
    if event_type not in _EVENT_TRANSITIONS:
        raise ValueError(f"Unknown event type: {event_type}")

    allowed_prior, _ = _EVENT_TRANSITIONS[event_type]
    if not allowed_prior:
        # PROPOSED has no prior-state requirement (handled at assignment creation)
        return
    if current_status not in allowed_prior:
        raise ValueError(
            f"Event '{event_type.value}' is not valid when assignment is in "
            f"status '{current_status.value}'. "
            f"Allowed prior statuses: {[s.value for s in allowed_prior]}"
        )


def next_status_for_event(event_type: OperationEventType) -> AssignmentStatus:
    """Return the resulting AssignmentStatus after applying event_type."""
    return _EVENT_TRANSITIONS[event_type][1]


@runtime_checkable
class AssignmentRepository(Protocol):
    """Protocol for saving and querying rescue assignments."""

    def save(self, assignment: Assignment) -> Assignment:
        """Persist a new assignment and return it with any storage-generated fields."""
        ...

    def get_by_id(self, assignment_id: uuid.UUID) -> Optional[Assignment]:
        """Return the assignment for assignment_id, or None if not found."""
        ...

    def list_by_incident(self, incident_id: uuid.UUID) -> list[Assignment]:
        """Return all assignments for the given incident, newest first."""
        ...

    def update_status(
        self,
        assignment_id: uuid.UUID,
        status: AssignmentStatus,
        approved_at: Optional[datetime] = None,
    ) -> Optional[Assignment]:
        """Update assignment status (and optionally approved_at). Return updated, or None."""
        ...

    def save_event(self, event: OperationEvent) -> OperationEvent:
        """Persist an operation lifecycle event."""
        ...

    def list_events(self, assignment_id: uuid.UUID) -> list[OperationEvent]:
        """Return all events for the given assignment, oldest first."""
        ...


class InMemoryAssignmentRepository:
    """In-memory AssignmentRepository for unit tests."""

    def __init__(self) -> None:
        self._assignments: dict[uuid.UUID, Assignment] = {}
        self._events: dict[uuid.UUID, OperationEvent] = {}

    def save(self, assignment: Assignment) -> Assignment:
        self._assignments[assignment.id] = assignment
        return assignment

    def get_by_id(self, assignment_id: uuid.UUID) -> Optional[Assignment]:
        return self._assignments.get(assignment_id)

    def list_by_incident(self, incident_id: uuid.UUID) -> list[Assignment]:
        return sorted(
            [a for a in self._assignments.values() if a.incident_id == incident_id],
            key=lambda a: a.created_at,
            reverse=True,
        )

    def update_status(
        self,
        assignment_id: uuid.UUID,
        status: AssignmentStatus,
        approved_at: Optional[datetime] = None,
    ) -> Optional[Assignment]:
        existing = self._assignments.get(assignment_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "status": status,
                **({"approved_at": approved_at} if approved_at is not None else {}),
            }
        )
        self._assignments[assignment_id] = updated
        return updated

    def save_event(self, event: OperationEvent) -> OperationEvent:
        self._events[event.id] = event
        return event

    def list_events(self, assignment_id: uuid.UUID) -> list[OperationEvent]:
        return sorted(
            [e for e in self._events.values() if e.assignment_id == assignment_id],
            key=lambda e: e.created_at,
        )
