"""Landmark gazetteer search.

Finds landmarks whose names resemble a phrase from a report, optionally within
a radius of a point. Returns ranked candidates with the similarity that
produced each one. An empty result is a valid answer.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from raahat.adapters.maps.transliteration import generate_query_variants

MIN_SIMILARITY = 0.35
MAX_CANDIDATES_PER_PHRASE = 5

_SEARCH = text(
    """
    SELECT id, name, kind, salience, source, external_id,
           ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,
           GREATEST(similarity(lower(name), :q), word_similarity(:q, lower(name))) AS sim,
           CASE WHEN CAST(:lat AS double precision) IS NULL THEN NULL
                ELSE ST_Distance(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
           END AS distance_m
    FROM landmarks
    WHERE GREATEST(similarity(lower(name), :q), word_similarity(:q, lower(name))) >= :min_sim
      AND (
            CAST(:lat AS double precision) IS NULL
            OR ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
          )
    ORDER BY sim DESC, salience DESC, name
    LIMIT :limit
    """
)


@dataclass(frozen=True)
class LandmarkMatch:
    landmark_id: uuid.UUID
    name: str
    kind: str
    source: str
    external_id: Optional[str]
    latitude: float
    longitude: float
    similarity: float
    query: str
    distance_from_focus_m: Optional[float]


def search_landmarks(
    session: Session,
    phrase: str,
    *,
    focus: Optional[tuple[float, float]] = None,
    radius_m: float = 75_000.0,
    limit: int = MAX_CANDIDATES_PER_PHRASE,
    min_similarity: float = MIN_SIMILARITY,
) -> list[LandmarkMatch]:
    """Rank landmarks by name similarity to ``phrase``.

    ``focus`` is (lat, lon); when given, only landmarks within ``radius_m`` are
    considered. Transliteration variants of the phrase are tried and the best
    score per landmark kept.
    """
    phrase = phrase.strip()
    if len(phrase) < 3:
        return []
    best: dict[uuid.UUID, LandmarkMatch] = {}
    for variant in generate_query_variants(phrase)[:4]:
        rows = session.execute(
            _SEARCH,
            {
                "q": variant.lower(),
                "min_sim": min_similarity,
                "lat": focus[0] if focus else None,
                "lon": focus[1] if focus else None,
                "radius_m": radius_m,
                "limit": limit,
            },
        ).all()
        for row in rows:
            match = LandmarkMatch(
                landmark_id=row.id,
                name=row.name,
                kind=row.kind,
                source=row.source,
                external_id=row.external_id,
                latitude=float(row.lat),
                longitude=float(row.lon),
                similarity=round(float(row.sim), 3),
                query=phrase,
                distance_from_focus_m=float(row.distance_m) if row.distance_m is not None else None,
            )
            current = best.get(match.landmark_id)
            if current is None or match.similarity > current.similarity:
                best[match.landmark_id] = match
    return sorted(best.values(), key=lambda m: m.similarity, reverse=True)[:limit]
