"""Database repository implementations."""
from __future__ import annotations

from .assignment import PostgresAssignmentRepository
from .audit import (
    AuditRepository,
    InMemoryAuditRepository,
    PostgresAuditRepository,
    compute_audit_hash,
)
from .callback import (
    CallbackJobRepository,
    InMemoryCallbackJobRepository,
    PostgresCallbackJobRepository,
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
from .resource import PostgresResourceRepository

__all__ = [
    "PostgresAssignmentRepository",

    "AuditRepository",
    "CallbackJobRepository",
    "EvidenceRepository",
    "InMemoryAuditRepository",
    "InMemoryCallbackJobRepository",
    "InMemoryEvidenceRepository",
    "InMemoryLandmarkRepository",
    "InMemoryLocationHypothesisRepository",
    "LandmarkRepository",
    "LocationHypothesisRepository",
    "PostgresAuditRepository",
    "PostgresCallbackJobRepository",
    "PostgresEvidenceRepository",
    "PostgresLandmarkRepository",
    "PostgresLocationHypothesisRepository",
    "PostgresResourceRepository",
    "compute_audit_hash",
    "evidence_item_to_model",
    "model_to_evidence_item",
    "trigram_similarity",
]
