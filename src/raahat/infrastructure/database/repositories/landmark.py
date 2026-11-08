"""PostGIS-backed and in-memory landmark repositories with trigram fuzzy matching."""
from __future__ import annotations

import uuid
from typing import Optional, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from raahat.adapters.maps.transliteration import generate_query_variants
from raahat.domain.geospatial.landmark import BoundingBox, Landmark, LandmarkCandidate
from raahat.domain.shared.coordinates import PointCoordinates

# ---------------------------------------------------------------------------
# Trigram similarity utility
# ---------------------------------------------------------------------------


def _trigrams(s: str) -> set[str]:
    """Extract character trigrams with pg_trgm-style padding (2 leading, 1 trailing space)."""
    padded = f"  {s} "
    if len(padded) < 3:
        return set()
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def trigram_similarity(s1: str, s2: str) -> float:
    """Compute trigram Jaccard similarity matching PostgreSQL pg_trgm similarity()."""
    t1 = _trigrams(s1.lower())
    t2 = _trigrams(s2.lower())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LandmarkRepository(Protocol):
    """Read-only access to the indexed landmark store."""

    def search_by_text(
        self,
        query: str,
        bounding_box: Optional[BoundingBox],
        max_results: int,
        similarity_threshold: float,
    ) -> list[LandmarkCandidate]: ...

    def find_within_radius(
        self,
        center: PointCoordinates,
        radius_m: float,
        kind_filter: Optional[str],
        max_results: int,
    ) -> list[LandmarkCandidate]: ...


# ---------------------------------------------------------------------------
# SQL queries for PostgreSQL / PostGIS
# ---------------------------------------------------------------------------

_SEARCH_BY_TEXT_SQL = text(
    """
    SELECT
        id,
        name,
        kind,
        salience,
        ST_X(location::geometry) AS longitude,
        ST_Y(location::geometry) AS latitude,
        external_id,
        metadata,
        similarity(name, :query) AS sim
    FROM landmarks
    WHERE
        similarity(name, :query) >= :threshold
        AND (
            :bbox_enabled = FALSE
            OR ST_Within(
                location::geometry,
                ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326)
            )
        )
    ORDER BY sim DESC, salience DESC
    LIMIT :max_results
    """
)

_FIND_WITHIN_RADIUS_SQL = text(
    """
    SELECT
        id,
        name,
        kind,
        salience,
        ST_X(location::geometry) AS longitude,
        ST_Y(location::geometry) AS latitude,
        external_id,
        metadata,
        ST_Distance(location, ST_MakePoint(:lon, :lat)::geography) AS distance_m
    FROM landmarks
    WHERE
        ST_DWithin(location, ST_MakePoint(:lon, :lat)::geography, :radius_m)
        AND (cast(:kind_filter as text) IS NULL OR kind = cast(:kind_filter as text))
    ORDER BY distance_m ASC, salience DESC
    LIMIT :max_results
    """
)


def _row_to_landmark(row: object) -> Landmark:
    """Convert a raw SQL result row to a Landmark domain object."""
    return Landmark(
        id=uuid.UUID(str(row.id)),  # type: ignore[attr-defined]
        name=row.name,  # type: ignore[attr-defined]
        kind=row.kind,  # type: ignore[attr-defined]
        location=PointCoordinates(
            latitude=float(row.latitude),  # type: ignore[attr-defined]
            longitude=float(row.longitude),  # type: ignore[attr-defined]
        ),
        salience=float(row.salience),  # type: ignore[attr-defined]
        external_id=row.external_id,  # type: ignore[attr-defined]
        metadata=dict(row.metadata) if row.metadata else {},  # type: ignore[attr-defined]
    )


# ---------------------------------------------------------------------------
# PostgreSQL implementation
# ---------------------------------------------------------------------------


class PostgresLandmarkRepository:
    """LandmarkRepository backed by PostgreSQL/PostGIS with pg_trgm indexing."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def search_by_text(
        self,
        query: str,
        bounding_box: Optional[BoundingBox],
        max_results: int,
        similarity_threshold: float,
    ) -> list[LandmarkCandidate]:
        """Search landmarks by text using trigram similarity and optional bounding box.

        Runs all transliteration variants of the query and deduplicates results,
        keeping the highest score per landmark.
        """
        variants = generate_query_variants(query)
        seen: dict[uuid.UUID, LandmarkCandidate] = {}

        bbox_params: dict[str, object]
        if bounding_box is not None:
            bbox_params = {
                "bbox_enabled": True,
                "min_lon": bounding_box.min_longitude,
                "min_lat": bounding_box.min_latitude,
                "max_lon": bounding_box.max_longitude,
                "max_lat": bounding_box.max_latitude,
            }
        else:
            bbox_params = {
                "bbox_enabled": False,
                "min_lon": 0.0,
                "min_lat": 0.0,
                "max_lon": 0.0,
                "max_lat": 0.0,
            }

        with self._session_factory() as session:
            for variant in variants:
                params = {
                    "query": variant,
                    "threshold": similarity_threshold,
                    "max_results": max_results,
                    **bbox_params,
                }
                rows = session.execute(_SEARCH_BY_TEXT_SQL, params).fetchall()
                for row in rows:
                    landmark = _row_to_landmark(row)
                    sim = float(row.sim)  # type: ignore[attr-defined]
                    score = sim * landmark.salience
                    existing = seen.get(landmark.id)
                    if existing is None or score > existing.score:
                        seen[landmark.id] = LandmarkCandidate(
                            landmark=landmark,
                            similarity=sim,
                            distance_m=None,
                            score=score,
                        )

        candidates = sorted(seen.values(), key=lambda c: c.score, reverse=True)
        return candidates[:max_results]

    def find_within_radius(
        self,
        center: PointCoordinates,
        radius_m: float,
        kind_filter: Optional[str],
        max_results: int,
    ) -> list[LandmarkCandidate]:
        """Return landmarks within radius_m metres of center, ordered by distance."""
        with self._session_factory() as session:
            params = {
                "lon": center.longitude,
                "lat": center.latitude,
                "radius_m": radius_m,
                "kind_filter": kind_filter,
                "max_results": max_results,
            }
            rows = session.execute(_FIND_WITHIN_RADIUS_SQL, params).fetchall()

        return [
            LandmarkCandidate(
                landmark=_row_to_landmark(row),
                similarity=1.0,
                distance_m=float(row.distance_m),  # type: ignore[attr-defined]
                score=1.0 / (1.0 + float(row.distance_m)),  # type: ignore[attr-defined]
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryLandmarkRepository:
    """In-memory implementation of LandmarkRepository for unit testing and offline use."""

    def __init__(self, landmarks: list[Landmark] | None = None) -> None:
        self._landmarks: dict[uuid.UUID, Landmark] = {lm.id: lm for lm in (landmarks or [])}

    def add(self, landmark: Landmark) -> None:
        self._landmarks[landmark.id] = landmark

    def add_many(self, landmarks: list[Landmark]) -> None:
        for lm in landmarks:
            self._landmarks[lm.id] = lm

    def search_by_text(
        self,
        query: str,
        bounding_box: Optional[BoundingBox],
        max_results: int,
        similarity_threshold: float,
    ) -> list[LandmarkCandidate]:
        variants = generate_query_variants(query)
        best_candidates: dict[uuid.UUID, LandmarkCandidate] = {}

        for lm in self._landmarks.values():
            if bounding_box is not None and not bounding_box.contains(lm.location):
                continue

            best_sim = 0.0
            for variant in variants:
                sim = trigram_similarity(variant, lm.name)
                if sim > best_sim:
                    best_sim = sim

            if best_sim >= similarity_threshold:
                score = best_sim * lm.salience
                best_candidates[lm.id] = LandmarkCandidate(
                    landmark=lm,
                    similarity=best_sim,
                    distance_m=None,
                    score=score,
                )

        results = sorted(best_candidates.values(), key=lambda c: c.score, reverse=True)
        return results[:max_results]

    def find_within_radius(
        self,
        center: PointCoordinates,
        radius_m: float,
        kind_filter: Optional[str],
        max_results: int,
    ) -> list[LandmarkCandidate]:
        candidates: list[LandmarkCandidate] = []
        for lm in self._landmarks.values():
            if kind_filter is not None and lm.kind != kind_filter:
                continue
            dist = center.distance_to(lm.location)
            if dist <= radius_m:
                score = 1.0 / (1.0 + dist)
                candidates.append(
                    LandmarkCandidate(
                        landmark=lm,
                        similarity=1.0,
                        distance_m=dist,
                        score=score,
                    )
                )

        candidates.sort(key=lambda c: c.distance_m if c.distance_m is not None else float("inf"))
        return candidates[:max_results]
