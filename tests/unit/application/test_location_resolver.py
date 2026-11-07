"""Unit tests for LocationResolver and PostGISGazetteerResolver."""
from __future__ import annotations

import uuid

import pytest

from raahat.adapters.maps import InMemoryLandmarkRepository
from raahat.application.location import (
    ClarificationAnswer,
    LocationObservation,
    LocationResolver,
    PostGISGazetteerResolver,
)
from raahat.domain.geospatial.landmark import BoundingBox, Landmark
from raahat.domain.shared.coordinates import PointCoordinates


@pytest.fixture
def test_landmarks() -> list[Landmark]:
    return [
        Landmark(
            id=uuid.uuid4(),
            name="Shiv Mandir",
            kind="temple",
            location=PointCoordinates(latitude=18.5100, longitude=73.8540),
            salience=1.0,
            metadata={"ward": "central"},
        ),
        Landmark(
            id=uuid.uuid4(),
            name="Shiv Mandir",
            kind="temple",
            location=PointCoordinates(latitude=18.5800, longitude=73.9200),
            salience=0.9,
            metadata={"ward": "east"},
        ),
        Landmark(
            id=uuid.uuid4(),
            name="Saraswati Vidyalaya",
            kind="school",
            location=PointCoordinates(latitude=18.5200, longitude=73.8600),
            salience=0.8,
            metadata={"ward": "north"},
        ),
    ]


@pytest.fixture
def resolver(test_landmarks: list[Landmark]) -> PostGISGazetteerResolver:
    repo = InMemoryLandmarkRepository(test_landmarks)
    return PostGISGazetteerResolver(landmark_repo=repo)


def test_resolver_implements_protocol(resolver: PostGISGazetteerResolver) -> None:
    assert isinstance(resolver, LocationResolver)


@pytest.mark.asyncio
async def test_resolve_with_direct_coordinates(
    resolver: PostGISGazetteerResolver,
    test_landmarks: list[Landmark],
) -> None:
    # Point very close to first Shiv Mandir (within 50m)
    gps_point = PointCoordinates(latitude=18.5102, longitude=73.8541)
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        coordinates=gps_point,
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    top_hyp = resolution.hypotheses[0]
    assert top_hyp.coordinates == gps_point
    assert top_hyp.probability is None  # Never fabricate confidence!
    assert top_hyp.uncertainty_radius_m == 30.0
    assert "Shiv Mandir" in (top_hyp.candidate_label or "")
    assert resolution.clarification_question is None
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == test_landmarks[0].id


@pytest.mark.asyncio
async def test_resolve_single_landmark_proposes_relative_direction(
    resolver: PostGISGazetteerResolver,
    test_landmarks: list[Landmark],
) -> None:
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Saraswati Vidyalaya ke paas",
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    hyp = resolution.hypotheses[0]
    assert hyp.coordinates == test_landmarks[2].location
    assert hyp.probability is None
    assert hyp.uncertainty_radius_m == 150.0

    # Optimal question is relative direction
    q = resolution.clarification_question
    assert q is not None
    assert q.question_type == "relative_direction"
    assert "samne" in q.prompt_text.lower() and "peeche" in q.prompt_text.lower()
    assert "Samne (Front)" in q.options
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == test_landmarks[2].id


@pytest.mark.asyncio
async def test_resolve_single_landmark_with_relative_direction_answer(
    resolver: PostGISGazetteerResolver,
    test_landmarks: list[Landmark],
) -> None:
    # Caller originally said Saraswati Vidyalaya, and answers "samne"
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Saraswati Vidyalaya",
        answers=[
            ClarificationAnswer(
                question_id="q1",
                selected_option="Samne (Front)",
            )
        ],
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    hyp = resolution.hypotheses[0]
    assert hyp.coordinates == test_landmarks[2].location
    assert hyp.probability is None
    # Uncertainty tightened from 150m to 75m
    assert hyp.uncertainty_radius_m == 75.0
    assert "samne" in (hyp.candidate_label or "").lower()
    assert resolution.clarification_question is None


@pytest.mark.asyncio
async def test_resolve_ambiguous_landmarks_proposes_disambiguation(
    resolver: PostGISGazetteerResolver,
) -> None:
    # "Shiv Mandir" matches 2 distant temples (central vs east)
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Shiv Mandir ke paas",
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) >= 2
    assert all(h.probability is None for h in resolution.hypotheses)
    assert resolution.bounding_box is not None

    q = resolution.clarification_question
    assert q is not None
    assert q.question_type == "disambiguation"
    assert q.expected_information_gain is not None
    assert q.expected_information_gain > 0.5  # High EIG for binary ambiguity
    assert len(q.options) == 2
    assert any("central" in opt.lower() for opt in q.options)
    assert any("east" in opt.lower() for opt in q.options)


@pytest.mark.asyncio
async def test_resolve_ambiguity_resolved_by_prior_answer(
    resolver: PostGISGazetteerResolver,
    test_landmarks: list[Landmark],
) -> None:
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Shiv Mandir",
        answers=[
            ClarificationAnswer(
                question_id="q_dis",
                selected_option="Shiv Mandir (east)",
            )
        ],
    )

    resolution = await resolver.resolve(obs)

    # Filtered down to east Shiv Mandir
    assert len(resolution.hypotheses) == 1
    assert resolution.hypotheses[0].coordinates == test_landmarks[1].location
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == test_landmarks[1].id


@pytest.mark.asyncio
async def test_resolve_ambiguity_filtered_by_ward_code(
    resolver: PostGISGazetteerResolver,
    test_landmarks: list[Landmark],
) -> None:
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="Shiv Mandir",
        ward_code="central",
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    assert resolution.hypotheses[0].coordinates == test_landmarks[0].location
    assert resolution.resolved_landmark is not None
    assert resolution.resolved_landmark.id == test_landmarks[0].id


@pytest.mark.asyncio
async def test_resolve_no_match_fallback(
    resolver: PostGISGazetteerResolver,
) -> None:
    bbox = BoundingBox(
        min_latitude=18.50,
        min_longitude=73.80,
        max_latitude=18.60,
        max_longitude=73.90,
    )
    obs = LocationObservation(
        incident_id=uuid.uuid4(),
        raw_text="kisi anjaan jagah par",
        bounding_box=bbox,
    )

    resolution = await resolver.resolve(obs)

    assert len(resolution.hypotheses) == 1
    hyp = resolution.hypotheses[0]
    assert hyp.probability is None
    assert hyp.uncertainty_radius_m is not None and hyp.uncertainty_radius_m > 1000.0
    assert resolution.clarification_question is not None
    assert resolution.clarification_question.question_type == "general"
