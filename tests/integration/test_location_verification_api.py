"""Integration tests for location verification endpoint and hypothesis history."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import create_app
from raahat.api.dependencies import get_session_factory
from raahat.domain.shared.enums import VerificationStatus
from raahat.infrastructure.database.models import (
    AuditEventModel,
    DisasterModel,
    IncidentModel,
    LocationHypothesisModel,
)
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
        session.query(AuditEventModel).delete()
        session.query(LocationHypothesisModel).delete()
        session.query(IncidentModel).delete()
        session.query(DisasterModel).delete()
        session.commit()
        yield session


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seed_incident_and_hypotheses(
    db_session: Session,
) -> tuple[IncidentModel, list[LocationHypothesisModel]]:
    disaster = DisasterModel(
        id=uuid.uuid4(),
        name="Pune Floods 2026",
        disaster_type="flood",
    )
    db_session.add(disaster)

    incident = IncidentModel(
        id=uuid.uuid4(),
        disaster_id=disaster.id,
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    db_session.add(incident)

    hyp1 = LocationHypothesisModel(
        id=uuid.uuid4(),
        incident_id=incident.id,
        location="SRID=4326;POINT(73.8540 18.5100)",
        candidate_label="Shiv Mandir candidate",
        uncertainty_radius_m=150.0,
        verification_status="unverified",
    )
    hyp2 = LocationHypothesisModel(
        id=uuid.uuid4(),
        incident_id=incident.id,
        location="SRID=4326;POINT(73.8580 18.5140)",
        candidate_label="Gandhi Chowk candidate",
        uncertainty_radius_m=200.0,
        verification_status="unverified",
    )
    db_session.add_all([hyp1, hyp2])
    db_session.commit()

    return incident, [hyp1, hyp2]


def test_verify_existing_hypothesis_in_postgres(
    client: TestClient,
    db_session: Session,
    seed_incident_and_hypotheses: tuple[IncidentModel, list[LocationHypothesisModel]],
) -> None:
    incident, hypotheses = seed_incident_and_hypotheses
    hyp_to_verify = hypotheses[0]
    dispatcher_id = uuid.uuid4()

    res = client.post(
        f"/api/v1/incidents/{incident.id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id)},
        json={
            "hypothesis_id": str(hyp_to_verify.id),
            "uncertainty_radius_m": 0.0,
            "notes": "Confirmed on 112 callback with resident",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == str(incident.id)
    assert data["verified_hypothesis"]["id"] == str(hyp_to_verify.id)
    assert (
        data["verified_hypothesis"]["verification_status"]
        == VerificationStatus.CONFIRMED.value
    )
    assert data["total_hypotheses"] == 2

    # Verify PostgreSQL state directly
    db_session.expire_all()
    # 1. Hypotheses table: older hypothesis must NOT be deleted!
    all_rows = (
        db_session.query(LocationHypothesisModel)
        .filter_by(incident_id=incident.id)
        .all()
    )
    assert len(all_rows) == 2
    row_verified = [r for r in all_rows if r.id == hyp_to_verify.id][0]
    assert row_verified.verification_status == "confirmed"
    assert row_verified.uncertainty_radius_m == 0.0

    row_retained = [r for r in all_rows if r.id == hypotheses[1].id][0]
    assert row_retained.verification_status == "unverified"

    # 2. Incident table: status and last_confirmed_at updated
    inc_row = db_session.get(IncidentModel, incident.id)
    assert inc_row is not None
    assert inc_row.status == "verified"
    assert inc_row.last_confirmed_at is not None

    # 3. Audit events table: tamper-evident log created
    audit_row = db_session.get(AuditEventModel, uuid.UUID(data["audit_event_id"]))
    assert audit_row is not None
    assert audit_row.action == "incident.location_verified"
    assert audit_row.actor_id == dispatcher_id
    assert audit_row.entity_id == incident.id
    assert audit_row.hash is not None
    assert len(audit_row.hash) == 64


def test_verify_new_coordinates_and_audit_hash_chain(
    client: TestClient,
    db_session: Session,
    seed_incident_and_hypotheses: tuple[IncidentModel, list[LocationHypothesisModel]],
) -> None:
    incident, hypotheses = seed_incident_and_hypotheses
    dispatcher_id_1 = uuid.uuid4()
    dispatcher_id_2 = uuid.uuid4()

    # First verification
    res1 = client.post(
        f"/api/v1/incidents/{incident.id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id_1)},
        json={"hypothesis_id": str(hypotheses[0].id)},
    )
    assert res1.status_code == 200
    audit1_id = res1.json()["audit_event_id"]

    # Second verification with newly refined GPS pin coordinates
    res2 = client.post(
        f"/api/v1/incidents/{incident.id}/location/verify",
        headers={"X-Dispatcher-Id": str(dispatcher_id_2)},
        json={
            "coordinates": {"latitude": 18.5105, "longitude": 73.8545},
            "candidate_label": "Drone aerial verification pin",
            "uncertainty_radius_m": 5.0,
            "notes": "Refined pin from drone feed",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["total_hypotheses"] == 3  # 2 original + 1 newly added!

    # Verify earlier hypotheses were never deleted
    all_rows = (
        db_session.query(LocationHypothesisModel)
        .filter_by(incident_id=incident.id)
        .all()
    )
    assert len(all_rows) == 3

    # Verify cryptographic hash chaining on audit events
    audit1 = db_session.get(AuditEventModel, uuid.UUID(audit1_id))
    audit2 = db_session.get(AuditEventModel, uuid.UUID(data2["audit_event_id"]))
    assert audit1 is not None and audit2 is not None
    assert audit2.prev_hash == audit1.hash


def test_get_location_hypotheses_history_from_postgres(
    client: TestClient,
    seed_incident_and_hypotheses: tuple[IncidentModel, list[LocationHypothesisModel]],
) -> None:
    incident, _ = seed_incident_and_hypotheses

    res = client.get(f"/api/v1/incidents/{incident.id}/location/hypotheses")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == str(incident.id)
    assert data["total"] == 2
    assert len(data["hypotheses"]) == 2
