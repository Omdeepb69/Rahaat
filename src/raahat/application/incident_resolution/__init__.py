"""Incident resolution application package."""
from __future__ import annotations

from .matcher import (
    ConservativeIncidentMatcher,
    extract_coordinates,
    extract_name,
    extract_phone,
    normalize_phone,
)
from .models import (
    IncidentCandidate,
    IncidentSnapshot,
    MatchSignal,
    ResolutionDecision,
    ResolutionDecisionType,
    ResolutionResult,
)
from .protocol import IncidentMatcher, IncidentResolver
from .resolver import ConservativeIncidentResolver
from .service import IncidentResolutionService

__all__ = [
    "ConservativeIncidentMatcher",
    "ConservativeIncidentResolver",
    "IncidentCandidate",
    "IncidentMatcher",
    "IncidentResolutionService",
    "IncidentResolver",
    "IncidentSnapshot",
    "MatchSignal",
    "ResolutionDecision",
    "ResolutionDecisionType",
    "ResolutionResult",
    "extract_coordinates",
    "extract_name",
    "extract_phone",
    "normalize_phone",
]
