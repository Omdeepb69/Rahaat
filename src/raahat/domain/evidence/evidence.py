"""Evidence items, spans, and evidence graph domain models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import SourceType, VerificationStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceSpan(BaseModel):
    """Specific span in transcript or text payload supporting a claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    text: Optional[str] = None
    reference: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    """Decomposed factual claim extracted from a report with source provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    report_id: uuid.UUID
    subject_type: str
    subject_id: Optional[uuid.UUID] = None
    attribute: str
    value: Any
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    observed_at: Optional[datetime] = None
    spans: tuple[EvidenceSpan, ...] = Field(default_factory=tuple)


class Contradiction(BaseModel):
    """Conflict detected between two or more evidence items claiming incompatible facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    attribute: str
    subject_type: str
    evidence_item_ids: tuple[uuid.UUID, uuid.UUID]
    report_ids: tuple[uuid.UUID, uuid.UUID]
    conflict_type: str  # e.g., "trend_conflict", "headcount_divergence", "boolean_conflict", "numeric_divergence", "location_divergence"
    severity: str  # "high", "medium", "low"
    description: str
    values: dict[str, Any]  # mapping report_id (str) -> value
    detected_at: datetime = Field(default_factory=utc_now)


class Corroboration(BaseModel):
    """Two or more independent reports agreeing on the same factual claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    attribute: str
    subject_type: str
    evidence_item_ids: tuple[uuid.UUID, ...]
    report_ids: tuple[uuid.UUID, ...]
    value: Any
    agreement_count: int
    detected_at: datetime = Field(default_factory=utc_now)


class EvidenceProvenance(BaseModel):
    """Full provenance chain tracing an evidence item back to its origin report and channel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: uuid.UUID
    report_id: uuid.UUID
    source_type: SourceType
    source_identity: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    channel_reference: Optional[str] = None
    client_created_at: Optional[datetime] = None
    received_at: datetime
    attribute: str
    value: Any
    spans: tuple[EvidenceSpan, ...] = Field(default_factory=tuple)


class EvidenceGraph(BaseModel):
    """Graph of evidence items, corroborations, and contradictions across reports."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_ids: tuple[uuid.UUID, ...]
    evidence_items: tuple[EvidenceItem, ...]
    contradictions: tuple[Contradiction, ...] = Field(default_factory=tuple)
    corroborations: tuple[Corroboration, ...] = Field(default_factory=tuple)
