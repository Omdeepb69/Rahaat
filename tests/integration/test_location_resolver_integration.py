"""Integration tests for PostGISGazetteerResolver with PostgresLandmarkRepository."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.location import (
    ClarificationAnswer,
    LocationObservation,
    PostGISGazetteerResolver,
)
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
def postgis_resolver(
    session_factory: sessionmaker[Session],
    db_session: Session,
) -> tuple[PostGISGazetteerResolver, dict[str, uuid.UUID]]:
    # Seed known landmarks into live PostGIS
    lms = [
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
            name="Shiv Mandir",
            kind="temple",
            salience=0.9,
            location="SRID=4326;POINT(73.9200 18.5800)",  # ~10 km away
            metadata_={"ward": "east"},
        ),
        LandmarkModel(
            id=uuid.uuid4(),
            name="Saraswati Vidyalaya",
            kind="school",
            salience=0.85,
            location="SRID=4326;POINT(73.8560 18.5120)",
            metadata_={"ward": "north"},
        ),
    ]
    db_session.add_all(lms)
    db_session.commit()

    id_map = {f"{lm.name}_{lm.metadata_['ward']}": lm.id for lm in lms}
    repo = PostgresLandmarkRepository(session_factory)
    resolver = PostGISGazetteerResolver(landmark_repo=repo)
    return resolver, id_map


@pytest.mark.asyncio
async def test_postgis_resolver_direct_coordinates(
    postgis_resolver: tuple[PostGISGazetteerResolver, dict[str, uuid.UUID]],
) -> None:
    resolver, id_map = postgis_resolver
    # GPS coordinate 40m from Shiv Mandir central
    point = PointCoordinates(latitude=18.5103, longitude=73.8542)
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        coordinates=point,
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    assert resolution.hypotheses[0].coordinates == point
    assert resolution.hypotheses[0].probability is None
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == id_map["Shiv Mandir_central"]
    assert resolution.clarification_question is None


@pytest.mark.asyncio
async def test_postgis_resolver_fuzzy_text_single_landmark(
    postgis_resolver: tuple[PostGISGazetteerResolver, dict[str, uuid.UUID]],
) -> None:
    resolver, id_map = postgis_resolver
    # Fuzzy spelling of school
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="saraswati vidhyalay",
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == id_map["Saraswati Vidyalaya_north"]
    assert resolution.clarification_question is not None
    assert resolution.clarification_question.question_type == "relative_direction"


@pytest.mark.asyncio
async def test_postgis_resolver_disambiguation_flow(
    postgis_resolver: tuple[PostGISGazetteerResolver, dict[str, uuid.UUID]],
) -> None:
    resolver, id_map = postgis_resolver
    # Step 1: Initial call with ambiguous landmark "Shiv Mandir"
    obs1 = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Shiv Mandir",
    )
    res1 = await resolver.resolve(obs1)

    assert len(res1.hypotheses) >= 2
    q1 = res1.clarification_question
    assert q1 is not None
    assert q1.question_type == "disambiguation"
    assert q1.expected_information_gain is not None
    assert q1.expected_information_gain > 0.5

    # Step 2: Caller answers selecting east option
    obs2 = LocationObservation(
        incident_id=obs1.incident_id,
        raw_text="Shiv Mandir",
        answers=[
            ClarificationAnswer(
                question_id=q1.question_id,
                selected_option="Shiv Mandir (east)",
            )
        ],
    )
    res2 = await resolver.resolve(obs2)

    # Disambiguated down to east Shiv Mandir
    assert len(res2.hypotheses) == 1
    assert res2.resolved_landmark is not None
    assert res2.resolved_landmark.id == id_map["Shiv Mandir_east"]
    assert res2.clarification_question is not None
    assert res2.clarification_question.question_type == "relative_direction"

