"""Unit tests for location verification API route."""
from __future__ import annotations

import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from raahat.api.app import create_app
from raahat.api.dependencies import get_location_verification_service
from raahat.application.location import (
    LocationVerificationResult,
)
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import VerificationStatus


class StubLocationVerificationService:
    def __init__(self) -> None:
        self.incidents: dict[uuid.UUID, list[LocationHypothesis]] = {}

    def verify_location(
        self,
        incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        hypothesis_id: uuid.UUID | None = None,
        coordinates: PointCoordinates | None = None,
        candidate_label: str | None = None,
        uncertainty_radius_m: float | None = None,
        notes: str | None = None,
    ) -> LocationVerificationResult:
        if incident_id not in self.incidents:
            raise KeyError(f"Incident {incident_id} not found")

        hypotheses = self.incidents[incident_id]
        if hypothesis_id is not None:
            matching = [h for h in hypotheses if h.id == hypothesis_id]
            if not matching:
                raise KeyError(
                    f"Location hypothesis {hypothesis_id} not found for incident {incident_id}"
                )
            verified = LocationHypothesis(
                id=matching[0].id,
                incident_id=incident_id,
                coordinates=matching[0].coordinates,
                candidate_label=matching[0].candidate_label,
                uncertainty_radius_m=uncertainty_radius_m or 0.0,
                verification_status=VerificationStatus.CONFIRMED,
            )
        else:
            assert coordinates is not None
            verified = LocationHypothesis(
                incident_id=incident_id,
                coordinates=coordinates,
                candidate_label=candidate_label or "Verified pin",
                uncertainty_radius_m=uncertainty_radius_m or 0.0,
                verification_status=VerificationStatus.CONFIRMED,
            )
            hypotheses.append(verified)

        return LocationVerificationResult(
            incident_id=incident_id,
            verified_hypothesis=verified,
            audit_event_id=uuid.uuid4(),
            all_hypotheses=hypotheses,
        )

    def get_hypotheses_history(
        self, incident_id: uuid.UUID
    ) -> list[LocationHypothesis]:
        if incident_id not in self.incidents:
            raise KeyError(f"Incident {incident_id} not found")
        return self.incidents[incident_id]


@pytest.fixture
def stub_service() -> StubLocationVerificationService:
    return StubLocationVerificationService()


@pytest.fixture
def client(
    stub_service: StubLocationVerificationService,
) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_location_verification_service] = (
        lambda: stub_service
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_verify_location_requires_dispatcher_header(
    client: TestClient,
) -> None:
    incident_id = uuid.uuid4()
    # No X-Dispatcher-Id header
    res = client.post(
        f"/api/v1/incidents/{incident_id}/location/verify",
        json={"coordinates": {"latitude": 18.51, "longitude": 73.85}},
    )
    assert res.status_code == 401
    assert "Authenticated dispatcher identity required" in res.json()["detail"]


def test_verify_location_invalid_dispatcher_header_format(
    client: TestClient,
) -> None:
    incident_id = uuid.uuid4()
    res = client.post(
        f"/api/v1/incidents/{incident_id}/location/verify",
        headers={"X-Dispatcher-Id": "not-a-valid-uuid"},
        json={"coordinates": {"latitude": 18.51, "longitude": 73.85}},
    )
    assert res.status_code == 400
    assert "Invalid dispatcher UUID format" in res.json()["detail"]


def test_verify_location_missing_both_hypothesis_and_coords(
    client: TestClient,
) -> None:
    incident_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()
    res = client.post(
        f"/api/v1/incidents/{incident_id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id)},
        json={},
    )
    assert res.status_code == 422
    assert (
        "Either hypothesis_id or coordinates must be provided"
        in res.json()["detail"]
    )


def test_verify_location_incident_not_found(
    client: TestClient,
) -> None:
    incident_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()
    res = client.post(
        f"/api/v1/incidents/{incident_id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id)},
        json={"coordinates": {"latitude": 18.51, "longitude": 73.85}},
    )
    assert res.status_code == 404
    assert f"Incident {incident_id} not found" in res.json()["detail"]


def test_verify_location_success(
    client: TestClient,
    stub_service: StubLocationVerificationService,
) -> None:
    incident_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()
    hyp1 = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.51, longitude=73.85),
        candidate_label="Candidate 1",
    )
    stub_service.incidents[incident_id] = [hyp1]

    res = client.post(
        f"/api/v1/incidents/{incident_id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id)},
        json={
            "hypothesis_id": str(hyp1.id),
            "notes": "Confirmed by field volunteer",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == str(incident_id)
    assert data["verified_hypothesis"]["id"] == str(hyp1.id)
    assert (
        data["verified_hypothesis"]["verification_status"]
        == VerificationStatus.CONFIRMED.value
    )
    assert "audit_event_id" in data
    assert data["total_hypotheses"] == 1


def test_get_location_hypotheses_history(
    client: TestClient,
    stub_service: StubLocationVerificationService,
) -> None:
    incident_id = uuid.uuid4()
    hyp1 = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.51, longitude=73.85),
        candidate_label="Candidate 1",
    )
    hyp2 = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.52, longitude=73.86),
        candidate_label="Candidate 2",
    )
    stub_service.incidents[incident_id] = [hyp1, hyp2]

    res = client.get(f"/api/v1/incidents/{incident_id}/location/hypotheses")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == str(incident_id)
    assert data["total"] == 2
    assert len(data["hypotheses"]) == 2
