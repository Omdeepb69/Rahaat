"""Integration tests for rescue assignment lifecycle, state machine transitions, and dispatch API."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models import (
    AssignmentModel,
    DisasterModel,
    OperationEventModel,
    OutboxEventModel,
    ReportModel,
)
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.models.resource import ResourceModel
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
        session.query(OperationEventModel).delete()
        session.query(AssignmentModel).delete()
        session.query(EntityMergeEventModel).delete()
        session.query(AuditEventModel).delete()
        session.query(ResourceModel).delete()
        session.query(IncidentLinkModel).delete()
        session.query(IncidentReportModel).delete()
        session.query(LocationHypothesisModel).delete()
        session.query(IncidentModel).delete()
        session.query(OutboxEventModel).delete()
        session.query(ReportModel).delete()
        session.query(DisasterModel).delete()
        session.commit()
        yield session


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_incident_and_resource(
    db_session: Session,
    client: TestClient,
    dispatcher_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper: create a disaster, incident (via DB), and resource (via API). Return (incident_id, resource_id)."""
    disaster = DisasterModel(id=uuid.uuid4(), name="Flood 2026", disaster_type="flood")
    db_session.add(disaster)
    incident = IncidentModel(
        id=uuid.uuid4(),
        disaster_id=disaster.id,
        status="verified",
        operational_priority="urgent",
    )
    db_session.add(incident)
    db_session.commit()

    res = client.post(
        "/api/v1/resources",
        json={
            "disaster_id": str(disaster.id),
            "resource_type": "boat",
            "name": "Rescue Boat Alpha",
            "capacity": 8,
        },
        headers={"X-Dispatcher-Id": str(dispatcher_id)},
    )
    assert res.status_code == 201, res.text
    return incident.id, uuid.UUID(res.json()["id"])


class TestAssignmentLifecycleAPI:
    def test_propose_assignment_unauthorized_without_header(
        self, client: TestClient, db_session: Session
    ) -> None:
        incident_id = uuid.uuid4()
        payload = {"resource_id": str(uuid.uuid4())}
        res = client.post(f"/api/v1/incidents/{incident_id}/assignments", json=payload)
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_propose_assignment_success_and_persists(
        self,
        client: TestClient,
        db_session: Session,
        session_factory: sessionmaker[Session],
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)

        res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments",
            json={"resource_id": str(resource_id), "notes": "Dispatch boat to Sector 2"},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert res.status_code == 201, res.text
        data = res.json()

        assert data["assignment"]["status"] == "proposed"
        assert data["assignment"]["incident_id"] == str(incident_id)
        assert data["assignment"]["resource_id"] == str(resource_id)
        assert data["assignment"]["assigned_by"] == str(dispatcher_id)
        assert data["assignment"]["approved_at"] is None
        assert data["event"]["event_type"] == "proposed"
        assert data["event"]["actor_id"] == str(dispatcher_id)

        assignment_id = uuid.UUID(data["assignment"]["id"])

        # Verify PostgreSQL row
        with session_factory() as session:
            model = session.get(AssignmentModel, assignment_id)
            assert model is not None
            assert model.status == "proposed"
            assert model.incident_id == incident_id
            assert model.resource_id == resource_id

        # Verify audit event
        with session_factory() as session:
            audit = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_type == "assignment",
                    AuditEventModel.entity_id == assignment_id,
                    AuditEventModel.action == "assignment.proposed",
                )
            ).first()
            assert audit is not None
            assert audit.actor_id == dispatcher_id

    def test_approve_assignment_records_approved_at(
        self,
        client: TestClient,
        db_session: Session,
        session_factory: sessionmaker[Session],
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)

        # Propose
        propose_res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments",
            json={"resource_id": str(resource_id)},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert propose_res.status_code == 201
        assignment_id = propose_res.json()["assignment"]["id"]

        # Approve
        approve_res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments/{assignment_id}/events",
            json={"event_type": "approved", "notes": "Dispatcher authorized"},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert approve_res.status_code == 201, approve_res.text
        approve_data = approve_res.json()
        assert approve_data["assignment"]["status"] == "approved"
        assert approve_data["assignment"]["approved_at"] is not None
        assert approve_data["event"]["event_type"] == "approved"

        # Verify DB
        with session_factory() as session:
            model = session.get(AssignmentModel, uuid.UUID(assignment_id))
            assert model is not None
            assert model.status == "approved"
            assert model.approved_at is not None

    def test_invalid_transition_returns_409(
        self, client: TestClient, db_session: Session
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)

        propose_res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments",
            json={"resource_id": str(resource_id)},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assignment_id = propose_res.json()["assignment"]["id"]

        # Attempt EN_ROUTE directly from PROPOSED — invalid transition
        res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments/{assignment_id}/events",
            json={"event_type": "en_route"},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert res.status_code == 409
        assert "not valid when assignment is in status" in res.json()["detail"].lower()

    def test_full_lifecycle_proposed_through_rescued(
        self,
        client: TestClient,
        db_session: Session,
        session_factory: sessionmaker[Session],
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        propose_res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments",
            json={"resource_id": str(resource_id)},
            headers=headers,
        )
        assignment_id = propose_res.json()["assignment"]["id"]

        for event_type in ["approved", "acknowledged", "en_route", "on_scene", "rescued"]:
            res = client.post(
                f"/api/v1/incidents/{incident_id}/assignments/{assignment_id}/events",
                json={"event_type": event_type},
                headers=headers,
            )
            assert res.status_code == 201, f"{event_type}: {res.text}"

        final_data = res.json()
        assert final_data["assignment"]["status"] == "completed"

        # List events — should be proposed + 5 steps = 6
        events_res = client.get(
            f"/api/v1/incidents/{incident_id}/assignments/{assignment_id}/events"
        )
        assert events_res.status_code == 200
        events = events_res.json()
        assert len(events) == 6
        assert events[0]["event_type"] == "proposed"
        assert events[-1]["event_type"] == "rescued"

        # Verify audit chain: should have 6 events (1 proposed + 5 transitions)
        with session_factory() as session:
            audits = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_type == "assignment",
                    AuditEventModel.entity_id == uuid.UUID(assignment_id),
                )
            ).all()
            assert len(audits) == 6

    def test_get_assignment_404_for_wrong_incident(
        self, client: TestClient, db_session: Session
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)

        propose_res = client.post(
            f"/api/v1/incidents/{incident_id}/assignments",
            json={"resource_id": str(resource_id)},
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assignment_id = propose_res.json()["assignment"]["id"]

        # Request with wrong incident ID
        wrong_incident = uuid.uuid4()
        res = client.get(f"/api/v1/incidents/{wrong_incident}/assignments/{assignment_id}")
        assert res.status_code == 404

    def test_list_assignments_for_incident(
        self, client: TestClient, db_session: Session
    ) -> None:
        dispatcher_id = uuid.uuid4()
        incident_id, resource_id = _make_incident_and_resource(db_session, client, dispatcher_id)
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        # Propose two assignments
        for _ in range(2):
            # Register a fresh resource for each so FK constraints hold
            r = client.post(
                "/api/v1/resources",
                json={
                    "disaster_id": str(
                        db_session.query(DisasterModel).first().id  # type: ignore[union-attr]
                    ),
                    "resource_type": "boat",
                    "name": f"Boat-{uuid.uuid4().hex[:6]}",
                },
                headers=headers,
            )
            rid = r.json()["id"]
            client.post(
                f"/api/v1/incidents/{incident_id}/assignments",
                json={"resource_id": rid},
                headers=headers,
            )

        list_res = client.get(f"/api/v1/incidents/{incident_id}/assignments")
        assert list_res.status_code == 200
        assignments = list_res.json()
        assert len(assignments) >= 2
        all_incident_ids = {a["incident_id"] for a in assignments}
        assert all_incident_ids == {str(incident_id)}

