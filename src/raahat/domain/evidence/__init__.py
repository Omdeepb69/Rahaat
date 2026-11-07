"""Evidence domain package."""
from __future__ import annotations

from .detector import ContradictionDetector, RuleBasedContradictionDetector
from .evidence import (
    Contradiction,
    Corroboration,
    EvidenceGraph,
    EvidenceItem,
    EvidenceProvenance,
    EvidenceSpan,
)
from .extractor import ReportEvidenceExtractor, StructuredEvidenceExtractor
from .repository import EvidenceRepository, InMemoryEvidenceRepository
from .service import EvidenceGraphService

__all__ = [
    "Contradiction",
    "ContradictionDetector",
    "Corroboration",
    "EvidenceGraph",
    "EvidenceGraphService",
    "EvidenceItem",
    "EvidenceProvenance",
    "EvidenceRepository",
    "EvidenceSpan",
    "InMemoryEvidenceRepository",
    "ReportEvidenceExtractor",
    "RuleBasedContradictionDetector",
    "StructuredEvidenceExtractor",
]
