"""Incident domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import IncidentLinkType, IncidentStatus, PriorityLevel, RelationshipType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IncidentReportLink(BaseModel):
    """Many-to-many relationship linking a report to an incident."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: uuid.UUID
    report_id: uuid.UUID
    relationship: RelationshipType
    linked_by: str
    reviewed_by: Optional[uuid.UUID] = None
    created_at: datetime = Field(default_factory=utc_now)


class IncidentLink(BaseModel):
    """Potential relationship between two incidents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_a_id: uuid.UUID
    incident_b_id: uuid.UUID
    link_type: IncidentLinkType
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: str = "pending_review"
    created_at: datetime = Field(default_factory=utc_now)


class Incident(BaseModel):
    """Canonical operational incident aggregate inferred from reports."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    disaster_id: uuid.UUID
    status: IncidentStatus = IncidentStatus.UNVERIFIED
    operational_priority: PriorityLevel = PriorityLevel.UNASSESSED
    severity_facts: dict[str, Any] = Field(default_factory=dict)
    last_confirmed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

