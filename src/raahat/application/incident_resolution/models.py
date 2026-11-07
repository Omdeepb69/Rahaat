"""Domain and application models for conservative incident resolution."""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.incidents.incident import Incident
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import IncidentLinkType


class ResolutionDecisionType(str, Enum):
    """Actionable classification of how an incoming report maps to incidents."""

    AUTO_LINK = "auto_link"
    REQUIRES_REVIEW = "requires_review"
    CREATE_NEW = "create_new"


class MatchSignal(BaseModel):
    """An individual heuristic or evidence-based matching signal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., description="Identifier of the signal, e.g. phone_match, spatial_distance")
    weight: float = Field(..., ge=0.0, le=1.0, description="Relative weight of this signal in composite scoring")
    score: float = Field(..., ge=0.0, le=1.0, description="Evaluated score for this signal [0.0, 1.0]")
    detail: str = Field(default="", description="Human-readable explanation of the signal calculation")


class IncidentCandidate(BaseModel):
    """A potential existing incident matching an incoming report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: uuid.UUID
    score: float = Field(..., ge=0.0, le=1.0, description="Conservative composite match score")
    signals: list[MatchSignal] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list, description="Contradictions flagged between report and incident")
    spatial_distance_m: Optional[float] = Field(default=None, ge=0.0, description="Distance in metres if coordinates present")
    suggested_link_type: IncidentLinkType = Field(
        default=IncidentLinkType.POSSIBLE_DUPLICATE,
        description="Suggested link type if connected",
    )


class ResolutionDecision(BaseModel):
    """Outcome of conservative resolution evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: uuid.UUID
    decision_type: ResolutionDecisionType
    matched_incident_id: Optional[uuid.UUID] = None
    candidates: list[IncidentCandidate] = Field(default_factory=list)
    requires_review: bool = False
    suggested_link_type: Optional[IncidentLinkType] = None
    rationale: str = ""


class ResolutionResult(BaseModel):
    """Persisted outcome of processing a report through the resolution workflow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ResolutionDecision
    incident_id: uuid.UUID
    is_new_incident: bool
    link_id: Optional[uuid.UUID] = None


class IncidentSnapshot(BaseModel):
    """In-memory view of an incident with its attached hypotheses, reports, and evidence."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    incident: Incident
    hypotheses: list[LocationHypothesis] = Field(default_factory=list)
    reports: list[Report] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
