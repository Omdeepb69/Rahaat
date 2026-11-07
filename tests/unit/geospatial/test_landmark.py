"""Unit tests for landmark domain models, transliteration, and InMemoryLandmarkRepository."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from raahat.adapters.maps import (
    InMemoryLandmarkRepository,
    generate_query_variants,
    normalize_transliteration,
    trigram_similarity,
)
from raahat.domain.geospatial.landmark import BoundingBox, Landmark
from raahat.domain.shared.coordinates import PointCoordinates


def test_bounding_box_contains() -> None:
    bbox = BoundingBox(
        min_latitude=18.5,
        min_longitude=73.8,
        max_latitude=18.6,
        max_longitude=73.9,
    )
    # Point inside
    assert bbox.contains(PointCoordinates(latitude=18.55, longitude=73.85)) is True
    # Point on boundary
    assert bbox.contains(PointCoordinates(latitude=18.5, longitude=73.8)) is True
    assert bbox.contains(PointCoordinates(latitude=18.6, longitude=73.9)) is True
    # Points outside
    assert bbox.contains(PointCoordinates(latitude=18.49, longitude=73.85)) is False
    assert bbox.contains(PointCoordinates(latitude=18.61, longitude=73.85)) is False
    assert bbox.contains(PointCoordinates(latitude=18.55, longitude=73.79)) is False
    assert bbox.contains(PointCoordinates(latitude=18.55, longitude=73.91)) is False


def test_bounding_box_validation() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(
            min_latitude=-95.0,  # Invalid lat < -90
            min_longitude=73.8,
            max_latitude=18.6,
            max_longitude=73.9,
        )


def test_normalize_transliteration() -> None:
    # Double vowels
    assert normalize_transliteration("Shaanti") == "shanti"
    assert normalize_transliteration("Sheela") == "shila"
    assert normalize_transliteration("Roop") == "rup"
    # Ph / W
    assert normalize_transliteration("Phule") == "fule"
    assert normalize_transliteration("Wardha") == "vardha"
    # Punctuation and whitespace
    assert normalize_transliteration("  Shiv-Mandir,  Pune! ") == "shiv mandir pune"


def test_generate_query_variants() -> None:
    variants = generate_query_variants("Shiv Mandir")
    assert "shiv mandir" in variants
    # Synonym expansion
    assert any("temple" in v for v in variants)

    variants_bridge = generate_query_variants("Old Pul")
    assert any("bridge" in v for v in variants_bridge)


def test_trigram_similarity() -> None:
    # Exact match
    assert trigram_similarity("shiv mandir", "shiv mandir") == 1.0
    # Empty string
    assert trigram_similarity("", "shiv") == 0.0
    assert trigram_similarity("shiv", "") == 0.0
    # Typo similarity
    sim = trigram_similarity("shiv mandr", "shiv mandir")
    assert sim > 0.5
    # Disjoint strings
    assert trigram_similarity("abc", "xyz") == 0.0


def test_landmark_immutability() -> None:
    lm = Landmark(
        id=uuid.uuid4(),
        name="Shiv Mandir",
        kind="temple",
        location=PointCoordinates(latitude=18.51, longitude=73.85),
        salience=1.0,
    )
    with pytest.raises(ValidationError):
        lm.name = "Other"  # type: ignore[misc]


def test_in_memory_landmark_repository_text_search() -> None:
    lm1 = Landmark(
        id=uuid.uuid4(),
        name="Shiv Mandir",
        kind="temple",
        location=PointCoordinates(latitude=18.51, longitude=73.85),
        salience=1.0,
    )
    lm2 = Landmark(
        id=uuid.uuid4(),
        name="Gandhi Chowk",
        kind="chowk",
        location=PointCoordinates(latitude=18.52, longitude=73.86),
        salience=0.8,
    )
    repo = InMemoryLandmarkRepository([lm1, lm2])

    # Exact search
    results = repo.search_by_text("shiv mandir", bounding_box=None, max_results=5, similarity_threshold=0.3)
    assert len(results) == 1
    assert results[0].landmark.id == lm1.id
    assert results[0].similarity == 1.0

    # Fuzzy search with typo
    fuzzy_results = repo.search_by_text(
        "shiv mandr",
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(fuzzy_results) == 1
    assert fuzzy_results[0].landmark.id == lm1.id

    # Search with bounding box
    bbox_in = BoundingBox(min_latitude=18.50, min_longitude=73.80, max_latitude=18.515, max_longitude=73.855)
    bbox_out = BoundingBox(min_latitude=18.60, min_longitude=73.90, max_latitude=18.70, max_longitude=73.95)

    assert len(repo.search_by_text("shiv", bounding_box=bbox_in, max_results=5, similarity_threshold=0.3)) == 1
    assert len(repo.search_by_text("shiv", bounding_box=bbox_out, max_results=5, similarity_threshold=0.3)) == 0


def test_in_memory_landmark_repository_find_within_radius() -> None:
    center = PointCoordinates(latitude=18.51, longitude=73.85)
    # lm1: exactly at center
    lm1 = Landmark(
        id=uuid.uuid4(),
        name="Shiv Mandir",
        kind="temple",
        location=center,
        salience=1.0,
    )
    # lm2: ~150m away
    lm2 = Landmark(
        id=uuid.uuid4(),
        name="Ganesh Mandir",
        kind="temple",
        location=PointCoordinates(latitude=18.511, longitude=73.851),
        salience=0.9,
    )
    # lm3: ~5km away
    lm3 = Landmark(
        id=uuid.uuid4(),
        name="Distant School",
        kind="school",
        location=PointCoordinates(latitude=18.55, longitude=73.88),
        salience=0.7,
    )
    repo = InMemoryLandmarkRepository([lm1, lm2, lm3])

    # Find within 500m
    nearby = repo.find_within_radius(center=center, radius_m=500.0, kind_filter=None, max_results=10)
    assert len(nearby) == 2
    assert nearby[0].landmark.id == lm1.id  # closest first
    assert nearby[0].distance_m == pytest.approx(0.0, abs=1.0)
    assert nearby[1].landmark.id == lm2.id

    # Kind filter
    temples_only = repo.find_within_radius(center=center, radius_m=10_000.0, kind_filter="temple", max_results=10)
    assert len(temples_only) == 2
    assert all(c.landmark.kind == "temple" for c in temples_only)

    schools_only = repo.find_within_radius(center=center, radius_m=10_000.0, kind_filter="school", max_results=10)
    assert len(schools_only) == 1
    assert schools_only[0].landmark.id == lm3.id
