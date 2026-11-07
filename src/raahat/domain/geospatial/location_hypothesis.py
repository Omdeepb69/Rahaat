"""Location hypothesis domain model."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.coordinates import PointCoordinates
from ..shared.enums import VerificationStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocationHypothesis(BaseModel):
    """Candidate geographic location for an incident under uncertainty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    incident_id: uuid.UUID
    coordinates: PointCoordinates
    candidate_label: Optional[str] = None
    source_evidence_id: Optional[uuid.UUID] = None
    probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    uncertainty_radius_m: Optional[float] = Field(default=None, ge=0.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    created_at: datetime = Field(default_factory=utc_now)

