"""Landmark domain models and value objects."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.shared.coordinates import PointCoordinates


class BoundingBox(BaseModel):
    """Geographic bounding box defined by WGS84 coordinate bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_latitude: float = Field(..., ge=-90.0, le=90.0)
    min_longitude: float = Field(..., ge=-180.0, le=180.0)
    max_latitude: float = Field(..., ge=-90.0, le=90.0)
    max_longitude: float = Field(..., ge=-180.0, le=180.0)

    def contains(self, point: PointCoordinates) -> bool:
        """Check if a point falls within the bounding box."""
        return (
            self.min_latitude <= point.latitude <= self.max_latitude
            and self.min_longitude <= point.longitude <= self.max_longitude
        )


class Landmark(BaseModel):
    """A geographic Point-of-Interest (temple, school, bridge, chowk, etc.)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    location: PointCoordinates
    salience: float = Field(default=1.0, ge=0.0)
    external_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LandmarkCandidate(BaseModel):
    """A landmark candidate matching a textual description, scored and bounded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    landmark: Landmark
    similarity: float = Field(..., ge=0.0, le=1.0, description="Trigram text similarity")
    distance_m: Optional[float] = Field(default=None, ge=0.0, description="Distance from query origin")
    score: float = Field(..., ge=0.0, description="Combined ranking score")

