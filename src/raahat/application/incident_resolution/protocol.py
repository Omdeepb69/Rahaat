"""Protocols for candidate matching and conservative incident resolution."""
from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.reports.report import Report

from .models import IncidentCandidate, ResolutionDecision


@runtime_checkable
class IncidentMatcher(Protocol):
    """Protocol for finding and ranking candidate incidents matching an incoming report."""

    def find_candidates(
        self,
        report: Report,
        evidence_items: Optional[list[EvidenceItem]] = None,
        session: Optional[Any] = None,
    ) -> list[IncidentCandidate]:
        """Evaluate active incidents in the disaster zone and return ranked candidates."""
        ...


@runtime_checkable
class IncidentResolver(Protocol):
    """Protocol for evaluating candidates into an operational resolution decision."""

    def evaluate(
        self,
        report: Report,
        candidates: list[IncidentCandidate],
    ) -> ResolutionDecision:
        """Evaluate candidate incidents and determine whether to auto-link, review, or create new."""
        ...
