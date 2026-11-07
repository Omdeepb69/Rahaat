"""Evidence items and spans domain models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import VerificationStatus


class EvidenceSpan(BaseModel):
    """Specific span in transcript or text payload supporting a claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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

