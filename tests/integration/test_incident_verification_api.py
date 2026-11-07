"""Integration tests for Incident verification, linking, and unmerge REST endpoints."""
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
from raahat.infrastructure.database.models import DisasterModel, OutboxEventModel, ReportModel
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
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
        session.query(EntityMergeEventModel).delete()
        session.query(AuditEventModel).delete()
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


@pytest.fixture
def test_disaster(db_session: Session) -> DisasterModel:
    disaster = DisasterModel(
        id=uuid.uuid4(),
        name="Verification API Flood 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()
    db_session.refresh(disaster)
    return disaster


def _create_incident(
    db_session: Session,
    disaster_id: uuid.UUID,
    status: str = "unverified",
    priority: str = "unassessed",
) -> IncidentModel:
    inc = IncidentModel(
        id=uuid.uuid4(),
        disaster_id=disaster_id,
        status=status,
        operational_priority=priority,
        severity_facts={},
    )
    db_session.add(inc)
    db_session.commit()
    db_session.refresh(inc)
    return inc


class TestIncidentVerificationAPI:
    def test_verify_incident_requires_dispatcher_header(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        inc = _create_incident(db_session, test_disaster.id)

        # 1. Missing header -> 401
        resp = client.post(
            f"/api/v1/incidents/{inc.id}/verify",
            json={"status": "verified"},
        )
        assert resp.status_code == 401
        assert "Authenticated dispatcher identity required" in resp.json()["detail"]

        # 2. Invalid UUID header -> 400
        resp = client.post(
            f"/api/v1/incidents/{inc.id}/verify",
            json={"status": "verified"},
            headers={"X-Dispatcher-Id": "invalid-uuid"},
        )
        assert resp.status_code == 400
        assert "Invalid dispatcher UUID format" in resp.json()["detail"]

    def test_verify_incident_success(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        inc = _create_incident(db_session, test_disaster.id)
        dispatcher_id = uuid.uuid4()

        payload = {
            "status": "verified",
            "notes": "Verified by ground team radio",
            "operational_priority": "urgent",
        }
        resp = client.post(
            f"/api/v1/incidents/{inc.id}/verify",
            json=payload,
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["incident_id"] == str(inc.id)
        assert data["status"] == "verified"
        assert data["operational_priority"] == "urgent"
        assert data["verified_by"] == str(dispatcher_id)
        assert "audit_event_id" in data

        # Verify DB updated
        db_session.expire_all()
        updated = db_session.get(IncidentModel, inc.id)
        assert updated is not None
        assert updated.status == "verified"
        assert updated.operational_priority == "urgent"
        assert updated.severity_facts.get("verification_notes") == "Verified by ground team radio"

        # Verify AuditEventModel exists
        audit = db_session.get(AuditEventModel, uuid.UUID(data["audit_event_id"]))
        assert audit is not None
        assert audit.action == "incident.verified"
        assert audit.actor_id == dispatcher_id

    def test_verify_incident_not_found_returns_404(
        self,
        client: TestClient,
    ) -> None:
        random_id = uuid.uuid4()
        resp = client.post(
            f"/api/v1/incidents/{random_id}/verify",
            json={"status": "verified"},
            headers={"X-Dispatcher-Id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_approve_merge_via_links_endpoint(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        inc1 = _create_incident(db_session, test_disaster.id)
        inc2 = _create_incident(db_session, test_disaster.id)

        # Attach report to inc1
        rep = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="web",
            raw_payload={"text": "water rising"},
            idempotency_key=f"rep-{uuid.uuid4().hex}",
        )
        db_session.add(rep)
        db_session.add(IncidentReportModel(
            incident_id=inc1.id,
            report_id=rep.id,
            relationship="direct",
            linked_by="seed",
        ))
        db_session.commit()

        dispatcher_id = uuid.uuid4()
        payload = {
            "target_incident_id": str(inc2.id),
            "action": "approve_merge",
            "reason": "Duplicate reports from identical location and household",
        }
        resp = client.post(
            f"/api/v1/incidents/{inc1.id}/links",
            json=payload,
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "approved"
        assert data["status"] == "active"
        assert data["source_incident_id"] == str(inc1.id)
        assert data["target_incident_id"] == str(inc2.id)
        assert data["reassigned_report_count"] == 1
        assert data["merge_event_id"] is not None

        # Verify DB state
        db_session.expire_all()
        merge_event_id = uuid.UUID(data["merge_event_id"])
        event = db_session.get(EntityMergeEventModel, merge_event_id)
        assert event is not None
        assert event.status == "active"

        # inc1 closed
        s_inc = db_session.get(IncidentModel, inc1.id)
        assert s_inc is not None
        assert s_inc.status == "closed"
        assert s_inc.severity_facts.get("merged_into") == str(inc2.id)

        # inc2 has the corroborating link
        stmt = select(IncidentReportModel).where(
            IncidentReportModel.incident_id == inc2.id,
            IncidentReportModel.report_id == rep.id,
        )
        t_link = db_session.scalars(stmt).first()
        assert t_link is not None
        assert t_link.relationship == "corroborating"

    def test_unmerge_endpoint_restores_original_incident(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        inc1 = _create_incident(db_session, test_disaster.id)
        inc2 = _create_incident(db_session, test_disaster.id)
        dispatcher_id = uuid.uuid4()

        # 1. Merge inc1 into inc2
        merge_resp = client.post(
            f"/api/v1/incidents/{inc1.id}/links",
            json={
                "target_incident_id": str(inc2.id),
                "action": "approve_merge",
                "reason": "Initial mistaken merge",
            },
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert merge_resp.status_code == 200
        merge_event_id = merge_resp.json()["merge_event_id"]

        # 2. Unmerge via /unmerge endpoint
        unmerge_resp = client.post(
            f"/api/v1/incidents/{inc1.id}/unmerge",
            json={
                "target_incident_id": str(inc2.id),
                "reason": "Dispatcher identified callers belong to two distinct households",
                "merge_event_id": merge_event_id,
            },
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )

        assert unmerge_resp.status_code == 200
        data = unmerge_resp.json()
        assert data["action"] == "unmerged"
        assert data["status"] == "reversed"
        assert data["merge_event_id"] == merge_event_id

        # Verify DB restored
        db_session.expire_all()
        event = db_session.get(EntityMergeEventModel, uuid.UUID(merge_event_id))
        assert event is not None
        assert event.status == "reversed"
        assert event.reversed_at is not None

        s_inc = db_session.get(IncidentModel, inc1.id)
        assert s_inc is not None
        assert s_inc.status == "unverified"
        assert "merged_into" not in s_inc.severity_facts

    def test_get_incident_detail_and_links(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        inc = _create_incident(db_session, test_disaster.id)

        # GET detail
        resp = client.get(f"/api/v1/incidents/{inc.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incident"]["id"] == str(inc.id)
        assert data["incident"]["disaster_id"] == str(test_disaster.id)

        # GET links
        links_resp = client.get(f"/api/v1/incidents/{inc.id}/links")
        assert links_resp.status_code == 200
        assert isinstance(links_resp.json(), list)

    def test_list_incidents_by_disaster(
        self,
        client: TestClient,
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        _create_incident(db_session, test_disaster.id, status="unverified")
        _create_incident(db_session, test_disaster.id, status="verified")

        resp = client.get(f"/api/v1/incidents?disaster_id={test_disaster.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

        # Filter by status
        resp_filtered = client.get(f"/api/v1/incidents?disaster_id={test_disaster.id}&status=verified")
        assert resp_filtered.status_code == 200
        data_filtered = resp_filtered.json()
        assert all(i["status"] == "verified" for i in data_filtered)
