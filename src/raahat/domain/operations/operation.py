"""Operations domain models: Resource, Assignment, OperationEvent."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.coordinates import PointCoordinates
from ..shared.enums import AssignmentStatus, OperationEventType, ResourceStatus, ResourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Resource(BaseModel):
    """A physical or human resource available for disaster response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    disaster_id: uuid.UUID
    resource_type: ResourceType
    name: str
    capacity: Optional[int] = Field(default=None, ge=1)
    availability_status: ResourceStatus = ResourceStatus.AVAILABLE
    location: Optional[PointCoordinates] = None
    created_at: datetime = Field(default_factory=utc_now)


class Assignment(BaseModel):
    """Assignment of a resource to an incident."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    resource_id: uuid.UUID
    assigned_by: uuid.UUID
    status: AssignmentStatus = AssignmentStatus.PROPOSED
    approved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class OperationEvent(BaseModel):
    """Immutable audit event recording a state transition within an operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    assignment_id: Optional[uuid.UUID] = None
    incident_id: uuid.UUID
    event_type: OperationEventType
    actor_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
