"""Domain models and value objects for location observation and active clarification."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.geospatial.landmark import BoundingBox, Landmark
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates


class ClarificationAnswer(BaseModel):
    """User response to a prior active clarification question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    selected_option: Optional[str] = None
    text_response: Optional[str] = None


class ClarificationQuestion(BaseModel):
    """Optimal disambiguation question to reduce spatial location uncertainty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    prompt_text: str
    question_type: str = Field(
        ...,
        description="Type: 'disambiguation', 'relative_direction', 'ward', or 'general'",
    )
    options: list[str] = Field(default_factory=list)
    candidate_landmark_ids: list[uuid.UUID] = Field(default_factory=list)
    expected_information_gain: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Expected Information Gain (in bits)",
    )


class LocationObservation(BaseModel):
    """Input observations collected from caller, message, or field report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    raw_text: Optional[str] = None
    coordinates: Optional[PointCoordinates] = None
    bounding_box: Optional[BoundingBox] = None
    ward_code: Optional[str] = None
    answers: list[ClarificationAnswer] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocationResolution(BaseModel):
    """Result of location disambiguation containing hypotheses and next question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypotheses: list[LocationHypothesis] = Field(default_factory=list)
    bounding_box: Optional[BoundingBox] = None
    uncertainty_radius_m: float = Field(..., ge=0.0)
    clarification_question: Optional[ClarificationQuestion] = None
    resolved_landmark: Optional[Landmark] = None
