"""Integration tests for PostgresLandmarkRepository and LandmarkIndexer against PostGIS."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raahat.adapters.maps import LandmarkIndexer
from raahat.domain.geospatial.gazetteer import City
from raahat.domain.geospatial.landmark import BoundingBox
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.infrastructure.database.models.location import LandmarkModel
from raahat.infrastructure.database.repositories import PostgresLandmarkRepository
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine(TEST_DB_URL)
    return get_sync_sessionmaker(engine)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        session.query(LandmarkModel).delete()
        session.commit()
        yield session


@pytest.fixture
def seeded_repo(
    session_factory: sessionmaker[Session],
    db_session: Session,
) -> tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]]:
    """Seed test landmarks with known names, kinds, and coordinates."""
    # Anchored around Pune central area: ~18.5100 N, 73.8540 E
    landmarks = [
        LandmarkModel(
            id=uuid.uuid4(),
            name="Shiv Mandir",
            kind="temple",
            salience=1.0,
            location="SRID=4326;POINT(73.8540 18.5100)",
            metadata_={"ward": "central"},
        ),
        LandmarkModel(
            id=uuid.uuid4(),
            name="Ganesh Mandir",
            kind="temple",
            salience=0.9,
            location="SRID=4326;POINT(73.8550 18.5110)",
            metadata_={"ward": "central"},
        ),
        LandmarkModel(
            id=uuid.uuid4(),
            name="Saraswati Vidyalaya",
            kind="school",
            salience=0.8,
            location="SRID=4326;POINT(73.8560 18.5120)",
            metadata_={"ward": "north"},
        ),
        LandmarkModel(
            id=uuid.uuid4(),
            name="Gandhi Chowk",
            kind="chowk",
            salience=0.85,
            location="SRID=4326;POINT(73.8580 18.5140)",
            metadata_={"ward": "north"},
        ),
        LandmarkModel(
            id=uuid.uuid4(),
            name="Distant Hospital",
            kind="hospital",
            salience=0.7,
            location="SRID=4326;POINT(73.9200 18.5800)",  # ~10 km away
            metadata_={"ward": "east"},
        ),
    ]
    db_session.add_all(landmarks)
    db_session.commit()

    id_map = {lm.name: lm.id for lm in landmarks}
    repo = PostgresLandmarkRepository(session_factory)
    return repo, id_map


def test_text_search_exact_match(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    candidates = repo.search_by_text(
        query="Shiv Mandir",
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.landmark.id == id_map["Shiv Mandir"]
    assert top.landmark.name == "Shiv Mandir"
    assert top.similarity == pytest.approx(1.0, abs=0.01)


def test_text_search_trigram_fuzzy(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    # Query with spelling error
    candidates = repo.search_by_text(
        query="shiv mandr",
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(candidates) >= 1
    assert candidates[0].landmark.id == id_map["Shiv Mandir"]
    assert candidates[0].similarity > 0.4


def test_text_search_transliteration_variant(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    # Query using synonym "temple" for "mandir"
    candidates = repo.search_by_text(
        query="shiv temple",
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(candidates) >= 1
    assert any(c.landmark.id == id_map["Shiv Mandir"] for c in candidates)


def test_text_search_bounding_box_filter(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    # Bounding box containing Pune central area
    bbox_central = BoundingBox(
        min_latitude=18.50,
        min_longitude=73.85,
        max_latitude=18.52,
        max_longitude=73.86,
    )
    # Bounding box in another region
    bbox_other = BoundingBox(
        min_latitude=18.60,
        min_longitude=73.90,
        max_latitude=18.70,
        max_longitude=74.00,
    )

    results_in = repo.search_by_text(
        query="Shiv Mandir",
        bounding_box=bbox_central,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(results_in) >= 1
    assert results_in[0].landmark.id == id_map["Shiv Mandir"]
    assert all(bbox_central.contains(c.landmark.location) for c in results_in)

    results_out = repo.search_by_text(
        query="Shiv Mandir",
        bounding_box=bbox_other,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(results_out) == 0


def test_text_search_respects_similarity_threshold(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, _ = seeded_repo
    # Complete mismatch with high threshold
    results = repo.search_by_text(
        query="completely unrelated query xyz",
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.5,
    )
    assert len(results) == 0


def test_find_within_radius_returns_nearby(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    center = PointCoordinates(latitude=18.5100, longitude=73.8540)

    # 500m radius around Shiv Mandir
    results = repo.find_within_radius(
        center=center,
        radius_m=500.0,
        kind_filter=None,
        max_results=10,
    )
    # Shiv Mandir (0m) and Ganesh Mandir (~150m) should be within 500m
    ids = [c.landmark.id for c in results]
    assert id_map["Shiv Mandir"] in ids
    assert id_map["Ganesh Mandir"] in ids
    # Results should be sorted by distance ascending
    assert results[0].landmark.id == id_map["Shiv Mandir"]
    assert results[0].distance_m is not None
    assert results[0].distance_m < 1.0


def test_find_within_radius_excludes_distant(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    center = PointCoordinates(latitude=18.5100, longitude=73.8540)

    results = repo.find_within_radius(
        center=center,
        radius_m=1000.0,
        kind_filter=None,
        max_results=10,
    )
    # Distant Hospital (~10 km) should be excluded
    ids = [c.landmark.id for c in results]
    assert id_map["Distant Hospital"] not in ids


def test_kind_filter(
    seeded_repo: tuple[PostgresLandmarkRepository, dict[str, uuid.UUID]],
) -> None:
    repo, id_map = seeded_repo
    center = PointCoordinates(latitude=18.5100, longitude=73.8540)

    # Filter to schools only within 2 km
    results = repo.find_within_radius(
        center=center,
        radius_m=2000.0,
        kind_filter="school",
        max_results=10,
    )
    assert len(results) == 1
    assert results[0].landmark.id == id_map["Saraswati Vidyalaya"]
    assert results[0].landmark.kind == "school"


def test_indexer_seed_from_city(
    session_factory: sessionmaker[Session],
    db_session: Session,
) -> None:
    city = City(seed=42, n_pois=50)
    indexer = LandmarkIndexer(session_factory)
    inserted = indexer.seed_from_city(city)

    assert inserted == 50

    # Query the seeded landmarks via repository
    repo = PostgresLandmarkRepository(session_factory)
    sample_name = city.poi_names[0]
    results = repo.search_by_text(
        query=sample_name,
        bounding_box=None,
        max_results=5,
        similarity_threshold=0.3,
    )
    assert len(results) >= 1
    assert results[0].similarity > 0.5
