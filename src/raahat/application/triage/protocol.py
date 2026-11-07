"""Fact extractor and triage service protocols."""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from raahat.domain.evidence.evidence import Contradiction, EvidenceGraph, EvidenceItem
from raahat.domain.triage.facts import SeverityFacts


@runtime_checkable
class FactExtractor(Protocol):
    """Protocol for extracting normalized SeverityFacts from evidence items or graphs."""

    def extract_from_graph(self, graph: EvidenceGraph) -> SeverityFacts:
        """Extract SeverityFacts from a consolidated EvidenceGraph."""
        ...

    def extract_from_evidence(
        self,
        evidence_items: Sequence[EvidenceItem],
        contradictions: Sequence[Contradiction] = (),
        total_reports: int = 0,
        unverified_reports_count: int = 0,
    ) -> SeverityFacts:
        """Extract SeverityFacts from raw evidence items and contradiction records."""
        ...
