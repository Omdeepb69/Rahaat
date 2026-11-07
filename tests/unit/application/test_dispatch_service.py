"""Unit tests for DispatchService: assignment lifecycle, state machine, and audit events."""
from __future__ import annotations

import uuid

import pytest

from raahat.application.dispatch import DispatchService
from raahat.domain.operations import InMemoryAssignmentRepository
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType
from raahat.infrastructure.database.repositories.audit import InMemoryAuditRepository


@pytest.fixture()
def service() -> DispatchService:
    return DispatchService(
        assignment_repo=InMemoryAssignmentRepository(),
        audit_repo=InMemoryAuditRepository(),
    )


class TestProposeAssignment:
    def test_propose_creates_proposed_assignment(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        dispatcher_id = uuid.uuid4()

        assignment, event = service.propose_assignment(
            incident_id=incident_id,
            resource_id=resource_id,
            dispatcher_id=dispatcher_id,
            notes="Initial boat dispatch",
        )

        assert assignment.status == AssignmentStatus.PROPOSED
        assert assignment.incident_id == incident_id
        assert assignment.resource_id == resource_id
        assert assignment.assigned_by == dispatcher_id
        assert assignment.approved_at is None

        assert event.event_type == OperationEventType.PROPOSED
        assert event.assignment_id == assignment.id
        assert event.incident_id == incident_id
        assert event.actor_id == dispatcher_id

    def test_propose_records_audit_event(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        dispatcher_id = uuid.uuid4()

        assignment, _ = service.propose_assignment(
            incident_id=incident_id,
            resource_id=resource_id,
            dispatcher_id=dispatcher_id,
        )

        audit_repo: InMemoryAuditRepository = service._audit_repo  # type: ignore[assignment]
        audit = audit_repo.get_latest_event("assignment", assignment.id)
        assert audit is not None
        assert audit.action == "assignment.proposed"
        assert audit.actor_id == dispatcher_id
        assert audit.payload["incident_id"] == str(incident_id)


class TestRecordEvent:
    def test_approve_transitions_to_approved(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        assignment, _ = service.propose_assignment(
            incident_id=incident_id,
            resource_id=uuid.uuid4(),
            dispatcher_id=uuid.uuid4(),
        )

        updated, event = service.record_event(
            assignment_id=assignment.id,
            event_type=OperationEventType.APPROVED,
            actor_id=uuid.uuid4(),
        )

        assert updated.status == AssignmentStatus.APPROVED
        assert updated.approved_at is not None
        assert event.event_type == OperationEventType.APPROVED

    def test_full_lifecycle_proposed_to_rescued(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        dispatcher = uuid.uuid4()

        assignment, _ = service.propose_assignment(
            incident_id=incident_id,
            resource_id=uuid.uuid4(),
            dispatcher_id=dispatcher,
        )
        a_id = assignment.id

        for step in [
            OperationEventType.APPROVED,
            OperationEventType.ACKNOWLEDGED,
            OperationEventType.EN_ROUTE,
            OperationEventType.ON_SCENE,
            OperationEventType.RESCUED,
        ]:
            updated, _ = service.record_event(
                assignment_id=a_id,
                event_type=step,
                actor_id=dispatcher,
            )

        assert updated.status == AssignmentStatus.COMPLETED

        events = service.list_events(a_id)
        # proposed + 5 steps
        assert len(events) == 6

    def test_invalid_transition_raises_value_error(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        assignment, _ = service.propose_assignment(
            incident_id=incident_id,
            resource_id=uuid.uuid4(),
            dispatcher_id=uuid.uuid4(),
        )

        # EN_ROUTE requires APPROVED, not PROPOSED
        with pytest.raises(ValueError, match="not valid when assignment is in status 'proposed'"):
            service.record_event(
                assignment_id=assignment.id,
                event_type=OperationEventType.EN_ROUTE,
                actor_id=uuid.uuid4(),
            )

    def test_record_event_on_nonexistent_assignment_raises(self, service: DispatchService) -> None:
        with pytest.raises(ValueError, match="not found"):
            service.record_event(
                assignment_id=uuid.uuid4(),
                event_type=OperationEventType.APPROVED,
                actor_id=uuid.uuid4(),
            )

    def test_list_events_returns_in_creation_order(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        dispatcher = uuid.uuid4()

        assignment, _ = service.propose_assignment(
            incident_id=incident_id,
            resource_id=uuid.uuid4(),
            dispatcher_id=dispatcher,
        )
        service.record_event(
            assignment_id=assignment.id,
            event_type=OperationEventType.APPROVED,
            actor_id=dispatcher,
        )

        events = service.list_events(assignment.id)
        assert len(events) == 2
        assert events[0].event_type == OperationEventType.PROPOSED
        assert events[1].event_type == OperationEventType.APPROVED

    def test_list_assignments_returns_newest_first(self, service: DispatchService) -> None:
        incident_id = uuid.uuid4()
        dispatcher = uuid.uuid4()
        resource_a = uuid.uuid4()
        resource_b = uuid.uuid4()

        a1, _ = service.propose_assignment(incident_id, resource_a, dispatcher)
        a2, _ = service.propose_assignment(incident_id, resource_b, dispatcher)

        assignments = service.list_assignments(incident_id)
        assert assignments[0].id == a2.id
        assert assignments[1].id == a1.id

