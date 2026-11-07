"""Operations API routes: rescue assignment creation and lifecycle event recording."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from raahat.api.dependencies import get_dispatch_service, require_dispatcher_id
from raahat.application.dispatch import DispatchService
from raahat.domain.operations.operation import Assignment, OperationEvent
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType

router = APIRouter(prefix="/incidents", tags=["operations"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ProposeAssignmentRequest(BaseModel):
    """Payload to propose a resource assignment for an incident."""

    model_config = ConfigDict(extra="forbid")

    resource_id: uuid.UUID
    notes: Optional[str] = Field(default=None, description="Dispatcher notes")


class RecordEventRequest(BaseModel):
    """Payload to record a lifecycle event against an existing assignment."""

    model_config = ConfigDict(extra="forbid")

    event_type: OperationEventType
    notes: Optional[str] = Field(default=None, description="Actor-provided notes")
    payload: dict[str, Any] = Field(default_factory=dict)


class AssignmentResponse(BaseModel):
    """Assignment representation returned by API endpoints."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID
    incident_id: uuid.UUID
    resource_id: uuid.UUID
    assigned_by: uuid.UUID
    status: AssignmentStatus
    approved_at: Optional[datetime]
    created_at: datetime


class OperationEventResponse(BaseModel):
    """Operation lifecycle event representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID
    assignment_id: Optional[uuid.UUID]
    incident_id: uuid.UUID
    event_type: OperationEventType
    actor_id: Optional[uuid.UUID]
    notes: Optional[str]
    payload: dict[str, Any]
    created_at: datetime


class AssignmentWithEventResponse(BaseModel):
    """Combined response returning an assignment alongside its triggering event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assignment: AssignmentResponse
    event: OperationEventResponse


def _assignment_response(assignment: Assignment) -> AssignmentResponse:
    return AssignmentResponse(
        id=assignment.id,
        incident_id=assignment.incident_id,
        resource_id=assignment.resource_id,
        assigned_by=assignment.assigned_by,
        status=assignment.status,
        approved_at=assignment.approved_at,
        created_at=assignment.created_at,
    )


def _event_response(event: OperationEvent) -> OperationEventResponse:
    return OperationEventResponse(
        id=event.id,
        assignment_id=event.assignment_id,
        incident_id=event.incident_id,
        event_type=event.event_type,
        actor_id=event.actor_id,
        notes=event.notes,
        payload=event.payload,
        created_at=event.created_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{incident_id}/assignments",
    response_model=AssignmentWithEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a resource assignment for an incident",
)
def propose_assignment(
    incident_id: uuid.UUID,
    payload: ProposeAssignmentRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: DispatchService = Depends(get_dispatch_service),
) -> AssignmentWithEventResponse:
    """Create a PROPOSED assignment for an incident with dispatcher authorization.

    The assignment starts in PROPOSED status. Use POST
    /incidents/{id}/assignments/{assignment_id}/events to advance the lifecycle.
    """
    assignment, event = service.propose_assignment(
        incident_id=incident_id,
        resource_id=payload.resource_id,
        dispatcher_id=dispatcher_id,
        notes=payload.notes,
    )
    return AssignmentWithEventResponse(
        assignment=_assignment_response(assignment),
        event=_event_response(event),
    )


@router.get(
    "/{incident_id}/assignments",
    response_model=list[AssignmentResponse],
    status_code=status.HTTP_200_OK,
    summary="List all assignments for an incident",
)
def list_assignments(
    incident_id: uuid.UUID,
    service: DispatchService = Depends(get_dispatch_service),
) -> list[AssignmentResponse]:
    """Return all assignments for the given incident, newest first."""
    assignments = service.list_assignments(incident_id)
    return [_assignment_response(a) for a in assignments]


@router.get(
    "/{incident_id}/assignments/{assignment_id}",
    response_model=AssignmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a specific assignment",
)
def get_assignment(
    incident_id: uuid.UUID,
    assignment_id: uuid.UUID,
    service: DispatchService = Depends(get_dispatch_service),
) -> AssignmentResponse:
    """Return the assignment for assignment_id.

    Returns 404 if the assignment does not exist or does not belong to incident_id.
    """
    assignment = service.get_assignment(assignment_id)
    if assignment is None or assignment.incident_id != incident_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found for incident {incident_id}",
        )
    return _assignment_response(assignment)


@router.post(
    "/{incident_id}/assignments/{assignment_id}/events",
    response_model=AssignmentWithEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a lifecycle event against an assignment",
)
def record_event(
    incident_id: uuid.UUID,
    assignment_id: uuid.UUID,
    payload: RecordEventRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: DispatchService = Depends(get_dispatch_service),
) -> AssignmentWithEventResponse:
    """Record a state-transition event (e.g. APPROVED, EN_ROUTE, RESCUED) for an assignment.

    Returns 404 if the assignment is not found, 409 if the transition is invalid.
    """
    # Verify incident ownership before accepting the event
    existing = service.get_assignment(assignment_id)
    if existing is None or existing.incident_id != incident_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found for incident {incident_id}",
        )

    try:
        updated, event = service.record_event(
            assignment_id=assignment_id,
            event_type=payload.event_type,
            actor_id=dispatcher_id,
            notes=payload.notes,
            payload=payload.payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return AssignmentWithEventResponse(
        assignment=_assignment_response(updated),
        event=_event_response(event),
    )


@router.get(
    "/{incident_id}/assignments/{assignment_id}/events",
    response_model=list[OperationEventResponse],
    status_code=status.HTTP_200_OK,
    summary="List all events for an assignment",
)
def list_events(
    incident_id: uuid.UUID,
    assignment_id: uuid.UUID,
    service: DispatchService = Depends(get_dispatch_service),
) -> list[OperationEventResponse]:
    """Return all operation lifecycle events for an assignment, oldest first."""
    assignment = service.get_assignment(assignment_id)
    if assignment is None or assignment.incident_id != incident_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found for incident {incident_id}",
        )
    events = service.list_events(assignment_id)
    return [_event_response(e) for e in events]

