"""Integration tests for incident triage policy, fact extraction, and API against PostgreSQL."""
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
from raahat.application.triage import IncidentTriageService
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.shared.enums import PriorityLevel
from raahat.infrastructure.database.models import DisasterModel, OutboxEventModel, ReportModel
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.evidence import (
    EvidenceItemModel,
    EvidenceSpanModel,
)
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
from raahat.infrastructure.database.repositories.evidence import PostgresEvidenceRepository
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
        session.query(EvidenceSpanModel).delete()
        session.query(EvidenceItemModel).delete()
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


class TestIncidentTriageIntegration:
    def test_triage_incident_api_endpoint(
        self, client: TestClient, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Flood 2026", disaster_type="flood")
        db_session.add(disaster)
        db_session.flush()

        rep = ReportModel(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            source_type="phone_call",
            source_identity="+919876543210",
            idempotency_key=str(uuid.uuid4()),
            raw_payload={"text": "Water entered ground floor, 4 trapped, baby needs food"},
        )
        db_session.add(rep)
        db_session.flush()

        inc = IncidentModel(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            status="unverified",
            operational_priority="unassessed",
            severity_facts={},
        )
        db_session.add(inc)
        db_session.flush()

        link = IncidentReportModel(
            incident_id=inc.id,
            report_id=rep.id,
            relationship="direct",
            linked_by="system",
        )
        db_session.add(link)
        db_session.commit()

        # Add evidence items via PostgresEvidenceRepository
        evidence_repo = PostgresEvidenceRepository(session_factory)
        evidence_repo.save_all([
            EvidenceItem(
                report_id=rep.id,
                subject_type="environment",
                attribute="water_level_trend",
                value="rising",
            ),
            EvidenceItem(
                report_id=rep.id,
                subject_type="environment",
                attribute="water_depth_cm",
                value=120.0,
            ),
            EvidenceItem(
                report_id=rep.id,
                subject_type="household",
                attribute="trapped_status",
                value=True,
            ),
            EvidenceItem(
                report_id=rep.id,
                subject_type="need",
                attribute="relief_need",
                value="baby food for infant",
            ),
        ])

        # Call POST /api/v1/incidents/{incident_id}/triage
        response = client.post(f"/api/v1/incidents/{inc.id}/triage")
        assert response.status_code == 200
        data = response.json()

        assert data["incident_id"] == str(inc.id)
        assert data["operational_priority"] == "critical_review"
        assert "rising_water_with_trapped_occupants" in data["reasons"]
        assert data["requires_human_review"] is True
        assert data["severity_facts"]["water_level_trend"] == "rising"
        assert data["severity_facts"]["trapped_status"] is True
        assert data["severity_facts"]["water_depth_cm"] == 120.0

        # Verify incident updated in PostgreSQL
        with session_factory() as session:
            updated_inc = session.get(IncidentModel, inc.id)
            assert updated_inc is not None
            assert updated_inc.operational_priority == "critical_review"
            assert updated_inc.severity_facts["trapped_status"] is True

            # Verify AuditEventModel in PostgreSQL
            audit = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_type == "incident",
                    AuditEventModel.entity_id == inc.id,
                    AuditEventModel.action == "incident.triaged",
                )
            ).first()
            assert audit is not None
            assert audit.payload["new_priority"] == "critical_review"
            assert audit.hash is not None

    def test_triage_incident_404_not_found(self, client: TestClient) -> None:
        non_existent_id = uuid.uuid4()
        response = client.post(f"/api/v1/incidents/{non_existent_id}/triage")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_triage_service_with_contradictions_in_postgres(
        self, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Monsoon 2026", disaster_type="flood")
        db_session.add(disaster)
        db_session.flush()

        rep1 = ReportModel(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            source_type="phone_call",
            source_identity="+919876543211",
            idempotency_key=str(uuid.uuid4()),
            raw_payload={},
        )
        rep2 = ReportModel(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            source_type="sms",
            source_identity="+919876543212",
            idempotency_key=str(uuid.uuid4()),
            raw_payload={},
        )
        db_session.add_all([rep1, rep2])
        db_session.flush()

        inc = IncidentModel(
            id=uuid.uuid4(),
            disaster_id=disaster.id,
            status="unverified",
            operational_priority="unassessed",
            severity_facts={},
        )
        db_session.add(inc)
        db_session.flush()

        db_session.add(IncidentReportModel(incident_id=inc.id, report_id=rep1.id, relationship="direct", linked_by="test"))
        db_session.add(IncidentReportModel(incident_id=inc.id, report_id=rep2.id, relationship="direct", linked_by="test"))
        db_session.commit()

        # Add conflicting headcount evidence items
        evidence_repo = PostgresEvidenceRepository(session_factory)
        evidence_repo.save_all([
            EvidenceItem(report_id=rep1.id, subject_type="hh", attribute="people_count", value=2),
            EvidenceItem(report_id=rep2.id, subject_type="hh", attribute="people_count", value=15),
        ])

        audit_repo = PostgresAuditRepository(session_factory)
        service = IncidentTriageService(
            evidence_repo=evidence_repo,
            audit_repo=audit_repo,
            session_factory=session_factory,
        )

        updated_inc, assessment = service.triage_incident(inc.id)
        assert updated_inc.operational_priority == PriorityLevel.CRITICAL_REVIEW
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "evidence_contradiction_detected" in assessment.reasons
        assert assessment.requires_human_review is True
