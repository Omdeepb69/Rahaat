"""Triage assessment domain models."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import PriorityLevel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PriorityAssessment(BaseModel):
    """Deterministic, explainable operational priority assessment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    priority: PriorityLevel
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    unknown_fields: tuple[str, ...] = Field(default_factory=tuple)
    requires_human_review: bool = True
    assessed_at: datetime = Field(default_factory=utc_now)

