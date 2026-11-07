"""Database repository implementations."""
from __future__ import annotations

from .audit import (
    AuditRepository,
    PostgresAuditRepository,
    compute_audit_hash,
)
from .evidence import (
    EvidenceRepository,
    InMemoryEvidenceRepository,
    PostgresEvidenceRepository,
    evidence_item_to_model,
    model_to_evidence_item,
)
from .landmark import (
    InMemoryLandmarkRepository,
    LandmarkRepository,
    PostgresLandmarkRepository,
    trigram_similarity,
)
from .location_hypothesis import (
    InMemoryLocationHypothesisRepository,
    LocationHypothesisRepository,
    PostgresLocationHypothesisRepository,
)

__all__ = [
    "AuditRepository",
    "EvidenceRepository",
    "InMemoryEvidenceRepository",
    "InMemoryLandmarkRepository",
    "InMemoryLocationHypothesisRepository",
    "LandmarkRepository",
    "LocationHypothesisRepository",
    "PostgresAuditRepository",
    "PostgresEvidenceRepository",
    "PostgresLandmarkRepository",
    "PostgresLocationHypothesisRepository",
    "compute_audit_hash",
    "evidence_item_to_model",
    "model_to_evidence_item",
    "trigram_similarity",
]
