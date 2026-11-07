"""Landmark indexer: seeds the PostGIS landmarks table from synthetic City data."""
from __future__ import annotations

import math
import uuid

from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.geospatial.gazetteer import City
from raahat.infrastructure.database.models.location import LandmarkModel

# Default geographic origin for synthetic City grid (south-west corner).
# 6 km × 6 km grid anchored at Pune, Maharashtra for simulation/testing.
_ORIGIN_LAT = 18.5100  # degrees north
_ORIGIN_LON = 73.8540  # degrees east
_METRES_PER_DEGREE_LAT = 111_320.0  # approximate, varies ±0.3% across latitudes


def _metres_to_degrees(x_m: float, y_m: float, origin_lat: float, origin_lon: float) -> tuple[float, float]:
    """Convert local metric (x, y) offsets to WGS84 (lat, lon) using flat-earth approximation.

    Accurate to within ~1 m over a 6 km grid.
    """
    lat = origin_lat + y_m / _METRES_PER_DEGREE_LAT
    lon_scale = _METRES_PER_DEGREE_LAT * math.cos(math.radians(origin_lat))
    lon = origin_lon + x_m / lon_scale
    return lat, lon


class LandmarkIndexer:
    """Loads synthetic City landmarks into the PostgreSQL landmarks table.

    Used to seed test data and for local simulation; production loading
    would fetch real OSM data via a separate adapter.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def seed_from_city(
        self,
        city: City,
        origin_lat: float = _ORIGIN_LAT,
        origin_lon: float = _ORIGIN_LON,
        batch_size: int = 500,
    ) -> int:
        """Insert all City POIs into the landmarks table.

        Existing landmarks are NOT cleared; call this only on a clean table or
        inside a test-scoped transaction that will be rolled back.

        Returns the number of rows inserted.
        """
        rows: list[LandmarkModel] = []
        for i in range(city.n_pois):
            x_m, y_m = float(city.xy[i, 0]), float(city.xy[i, 1])
            lat, lon = _metres_to_degrees(x_m, y_m, origin_lat, origin_lon)
            wkt = f"SRID=4326;POINT({lon:.7f} {lat:.7f})"
            rows.append(
                LandmarkModel(
                    id=uuid.uuid4(),
                    name=city.poi_names[i],
                    kind=city.kind_of[i],
                    salience=float(city.salience[i]),
                    location=wkt,
                    metadata_={},
                )
            )

        inserted = 0
        with self._session_factory() as session:
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]
                session.add_all(batch)
                session.flush()
                inserted += len(batch)
            session.commit()

        return inserted

