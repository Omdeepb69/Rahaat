"""Geographic coordinate value objects."""
from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field


class PointCoordinates(BaseModel):
    """Geographic WGS84 point coordinate (latitude, longitude)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees (-90 to 90)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees (-180 to 180)")

    def to_wkt(self) -> str:
        """PostGIS EWKT representation (POINT(longitude latitude))."""
        return f"POINT({self.longitude:.7f} {self.latitude:.7f})"

    @classmethod
    def from_wkt(cls, wkt: str) -> PointCoordinates:
        match = re.search(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", wkt, re.IGNORECASE)
        if not match:
            raise ValueError(f"Invalid WKT point format: {wkt}")
        lon, lat = float(match.group(1)), float(match.group(2))
        return cls(latitude=lat, longitude=lon)

    def distance_to(self, other: PointCoordinates) -> float:
        """Great-circle distance in metres using Haversine formula."""
        earth_radius_m = 6371000.0
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        dlat = math.radians(other.latitude - self.latitude)
        dlon = math.radians(other.longitude - self.longitude)

        a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return earth_radius_m * c

