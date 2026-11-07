"""Integration tests for audit events query, inspection, and tamper-evident cryptographic verification API."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
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


class TestAuditAPI:
    def test_list_events_unauthorized_without_dispatcher_header(
        self, client: TestClient, db_session: Session
    ) -> None:
        res = client.get("/api/v1/audit/events")
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_verify_unauthorized_without_dispatcher_header(
        self, client: TestClient, db_session: Session
    ) -> None:
        res = client.get("/api/v1/audit/verify")
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_query_audit_events_and_get_by_id(
        self, client: TestClient, db_session: Session
    ) -> None:
        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        # Register a resource to produce an audit record
        disaster = DisasterModel(id=uuid.uuid4(), name="Cyclone 2026", disaster_type="cyclone")
        db_session.add(disaster)
        db_session.commit()

        res_create = client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "boat",
                "name": "Panaji Rescue Boat",
            },
            headers=headers,
        )
        assert res_create.status_code == 201
        resource_id = res_create.json()["id"]

        # 1. Query audit events via GET /api/v1/audit/events
        audit_res = client.get("/api/v1/audit/events", headers=headers)
        assert audit_res.status_code == 200
        data = audit_res.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

        first_event = data["items"][0]
        assert first_event["action"] == "resource.registered"
        assert first_event["entity_type"] == "resource"
        assert first_event["entity_id"] == resource_id
        assert first_event["hash"] is not None
        event_id = first_event["id"]

        # 2. Query with filters
        filtered_res = client.get(
            f"/api/v1/audit/events?entity_type=resource&entity_id={resource_id}",
            headers=headers,
        )
        assert filtered_res.status_code == 200
        assert filtered_res.json()["total"] == 1

        # 3. Get specific event by ID
        single_res = client.get(f"/api/v1/audit/events/{event_id}", headers=headers)
        assert single_res.status_code == 200
        assert single_res.json()["id"] == event_id

        # 4. Unknown event returns 404
        not_found_res = client.get(f"/api/v1/audit/events/{uuid.uuid4()}", headers=headers)
        assert not_found_res.status_code == 404

    def test_verify_audit_chain_valid_and_tampered(
        self,
        client: TestClient,
        db_session: Session,
        session_factory: sessionmaker[Session],
    ) -> None:
        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

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

        # Create resource
        r = client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "boat",
                "name": "Audit Test Boat",
            },
            headers=headers,
        )
        resource_id = r.json()["id"]

        # Propose and advance assignment lifecycle to produce multiple chained events
        assign_res = client.post(
            f"/api/v1/incidents/{incident.id}/assignments",
            json={"resource_id": resource_id},
            headers=headers,
        )
        assignment_id = assign_res.json()["assignment"]["id"]

        client.post(
            f"/api/v1/incidents/{incident.id}/assignments/{assignment_id}/events",
            json={"event_type": "approved"},
            headers=headers,
        )
        client.post(
            f"/api/v1/incidents/{incident.id}/assignments/{assignment_id}/events",
            json={"event_type": "en_route"},
            headers=headers,
        )

        # 1. Verify entity chain via API (should be valid with 3 events: proposed, approved, en_route)
        verify_res = client.get(
            f"/api/v1/audit/verify?entity_type=assignment&entity_id={assignment_id}",
            headers=headers,
        )
        assert verify_res.status_code == 200
        v_data = verify_res.json()
        assert v_data["is_valid"] is True
        assert v_data["total_events"] == 3
        assert v_data["genesis_hash"] is not None
        assert v_data["latest_hash"] is not None
        assert v_data["error_message"] is None

        # 2. Global verification across all entities
        global_res = client.get("/api/v1/audit/verify", headers=headers)
        assert global_res.status_code == 200
        g_data = global_res.json()
        assert g_data["all_valid"] is True
        assert g_data["total_events"] >= 4  # 1 resource + 3 assignment events
        assert len(g_data["corrupted_chains"]) == 0

        # 3. Directly tamper with a PostgreSQL audit_events row (e.g. modify payload in DB)
        with session_factory() as session:
            ev = (
                session.query(AuditEventModel)
                .filter_by(entity_type="assignment", entity_id=uuid.UUID(assignment_id))
                .order_by(AuditEventModel.created_at.asc())
                .all()
            )[1]  # The approved event
            ev.payload = {"tampered": True, "notes": "maliciously altered"}
            session.commit()

        # 4. Verification must detect the tampering!
        tampered_verify_res = client.get(
            f"/api/v1/audit/verify?entity_type=assignment&entity_id={assignment_id}",
            headers=headers,
        )
        assert tampered_verify_res.status_code == 200
        tampered_data = tampered_verify_res.json()
        assert tampered_data["is_valid"] is False
        assert tampered_data["corrupted_event_id"] == str(ev.id)
        assert "tampered with" in tampered_data["error_message"].lower()

        # 5. Global verify also detects corruption
        global_tampered_res = client.get("/api/v1/audit/verify", headers=headers)
        assert global_tampered_res.status_code == 200
        gt_data = global_tampered_res.json()
        assert gt_data["all_valid"] is False
        assert len(gt_data["corrupted_chains"]) >= 1

    def test_verify_invalid_parameter_combination_returns_400(
        self, client: TestClient, db_session: Session
    ) -> None:
        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        # Only entity_type without entity_id
        res1 = client.get("/api/v1/audit/verify?entity_type=incident", headers=headers)
        assert res1.status_code == 400
        assert "both entity_type and entity_id" in res1.json()["detail"].lower()

        # Only entity_id without entity_type
        res2 = client.get(f"/api/v1/audit/verify?entity_id={uuid.uuid4()}", headers=headers)
        assert res2.status_code == 400
        assert "both entity_type and entity_id" in res2.json()["detail"].lower()
