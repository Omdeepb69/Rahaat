"""Unit tests for LocationVerificationService."""
from __future__ import annotations

import uuid
from typing import Optional

import pytest

from raahat.application.location.verification import LocationVerificationService
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import VerificationStatus
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import IncidentModel
from raahat.infrastructure.database.repositories.location_hypothesis import (
    InMemoryLocationHypothesisRepository,
)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEventModel] = []

    def record_event(
        self,
        action: str,
        actor_id: Optional[uuid.UUID],
        entity_type: str,
        entity_id: uuid.UUID,
        payload: dict,
    ) -> AuditEventModel:
        prev_hash = self.events[-1].hash if self.events else None
        event = AuditEventModel(
            id=uuid.uuid4(),
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            prev_hash=prev_hash,
            hash=f"hash_{len(self.events)}",
            payload=payload,
        )
        self.events.append(event)
        return event

    def get_latest_event(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Optional[AuditEventModel]:
        return self.events[-1] if self.events else None


class FakeSession:
    def __init__(self, incidents: dict[uuid.UUID, IncidentModel]) -> None:
        self.incidents = incidents

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def get(self, model_cls: type, ident: uuid.UUID) -> Optional[IncidentModel]:
        return self.incidents.get(ident)

    def commit(self) -> None:
        pass


def test_verify_existing_hypothesis_preserves_earlier_hypotheses() -> None:
    incident_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()

    incident = IncidentModel(
        id=incident_id,
        disaster_id=uuid.uuid4(),
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    session_factory = lambda: FakeSession({incident_id: incident})  # noqa: E731

    hyp1 = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.51, longitude=73.85),
        candidate_label="Candidate 1",
        uncertainty_radius_m=150.0,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    hyp2 = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.52, longitude=73.86),
        candidate_label="Candidate 2",
        uncertainty_radius_m=150.0,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    hypo_repo = InMemoryLocationHypothesisRepository([hyp1, hyp2])
    audit_repo = FakeAuditRepository()

    service = LocationVerificationService(
        session_factory=session_factory,  # type: ignore[arg-type]
        hypothesis_repo=hypo_repo,
        audit_repo=audit_repo,  # type: ignore[arg-type]
    )

    result = service.verify_location(
        incident_id=incident_id,
        dispatcher_id=dispatcher_id,
        hypothesis_id=hyp1.id,
        notes="Verified via radio confirmation",
    )

    # 1. Verified hypothesis has CONFIRMED status
    assert result.verified_hypothesis.id == hyp1.id
    assert result.verified_hypothesis.verification_status == VerificationStatus.CONFIRMED

    # 2. Earlier hypothesis hyp2 is NOT deleted
    assert len(result.all_hypotheses) == 2
    hyp2_retained = [h for h in result.all_hypotheses if h.id == hyp2.id][0]
    assert hyp2_retained.verification_status == VerificationStatus.UNVERIFIED

    # 3. Incident state updated
    assert incident.status == "verified"
    assert incident.last_confirmed_at is not None

    # 4. Audit event generated
    assert len(audit_repo.events) == 1
    assert audit_repo.events[0].action == "incident.location_verified"
    assert audit_repo.events[0].actor_id == dispatcher_id


def test_verify_with_new_coordinates_adds_hypothesis_without_erasing() -> None:
    incident_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()

    incident = IncidentModel(
        id=incident_id,
        disaster_id=uuid.uuid4(),
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    session_factory = lambda: FakeSession({incident_id: incident})  # noqa: E731

    old_hyp = LocationHypothesis(
        incident_id=incident_id,
        coordinates=PointCoordinates(latitude=18.51, longitude=73.85),
        candidate_label="Old Candidate",
        verification_status=VerificationStatus.UNVERIFIED,
    )
    hypo_repo = InMemoryLocationHypothesisRepository([old_hyp])
    audit_repo = FakeAuditRepository()

    service = LocationVerificationService(
        session_factory=session_factory,  # type: ignore[arg-type]
        hypothesis_repo=hypo_repo,
        audit_repo=audit_repo,  # type: ignore[arg-type]
    )

    new_coords = PointCoordinates(latitude=18.555, longitude=73.888)
    result = service.verify_location(
        incident_id=incident_id,
        dispatcher_id=dispatcher_id,
        coordinates=new_coords,
        candidate_label="Manual GPS pin",
        uncertainty_radius_m=15.0,
    )

    # New hypothesis created as CONFIRMED
    assert result.verified_hypothesis.coordinates == new_coords
    assert result.verified_hypothesis.verification_status == VerificationStatus.CONFIRMED

    # Old hypothesis still exists!
    assert len(result.all_hypotheses) == 2
    assert any(h.id == old_hyp.id for h in result.all_hypotheses)


def test_verify_location_validation_errors() -> None:
    incident_id = uuid.uuid4()
    incident = IncidentModel(
        id=incident_id,
        disaster_id=uuid.uuid4(),
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    session_factory = lambda: FakeSession({incident_id: incident})  # noqa: E731
    service = LocationVerificationService(
        session_factory=session_factory,  # type: ignore[arg-type]
        hypothesis_repo=InMemoryLocationHypothesisRepository([]),
        audit_repo=FakeAuditRepository(),  # type: ignore[arg-type]
    )

    # Missing both hypothesis_id and coordinates
    with pytest.raises(ValueError, match="Either hypothesis_id or coordinates"):
        service.verify_location(
            incident_id=incident_id,
            dispatcher_id=uuid.uuid4(),
        )

    # Incident does not exist
    missing_incident_id = uuid.uuid4()
    with pytest.raises(KeyError, match="Incident"):
        service.verify_location(
            incident_id=missing_incident_id,
            dispatcher_id=uuid.uuid4(),
            coordinates=PointCoordinates(latitude=18.5, longitude=73.8),
        )

    # Hypothesis does not exist for incident
    with pytest.raises(KeyError, match="Location hypothesis"):
        service.verify_location(
            incident_id=incident_id,
            dispatcher_id=uuid.uuid4(),
            hypothesis_id=uuid.uuid4(),
        )
