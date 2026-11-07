"""Location resolver protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import LocationObservation, LocationResolution


@runtime_checkable
class LocationResolver(Protocol):
    """Evaluates location observations and produces candidate hypotheses with clarification questions."""

    async def resolve(self, observation: LocationObservation) -> LocationResolution: ...
