"""Unit tests for IncidentReviewService merge, verify, and reversible unmerge workflows."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.incident_resolution.review import (
    IncidentReviewService,
    LinkReviewAction,
)
from raahat.domain.shared.enums import (
    IncidentStatus,
    PriorityLevel,
)
from raahat.infrastructure.database.models import DisasterModel, ReportModel
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import (
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.repositories.audit import InMemoryAuditRepository
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
def review_service_with_db(
    session_factory: sessionmaker[Session],
) -> tuple[IncidentReviewService, InMemoryAuditRepository, sessionmaker[Session]]:
    with session_factory() as session:
        session.query(EntityMergeEventModel).delete()
        session.query(AuditEventModel).delete()
        session.query(IncidentReportModel).delete()
        session.query(LocationHypothesisModel).delete()
        session.query(IncidentModel).delete()
        session.query(ReportModel).delete()
        session.query(DisasterModel).delete()
        session.commit()

    audit_repo = InMemoryAuditRepository()
    service = IncidentReviewService(session_factory=session_factory, audit_repo=audit_repo)
    return service, audit_repo, session_factory


def _seed_disaster_and_incidents(
    session: Session,
) -> tuple[DisasterModel, IncidentModel, IncidentModel, ReportModel]:
    disaster = DisasterModel(id=uuid.uuid4(), name="Test Flood", disaster_type="flood", status="active")
    session.add(disaster)

    inc1 = IncidentModel(
        id=uuid.uuid4(),
        disaster_id=disaster.id,
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    inc2 = IncidentModel(
        id=uuid.uuid4(),
        disaster_id=disaster.id,
        status="unverified",
        operational_priority="unassessed",
        severity_facts={},
    )
    session.add_all([inc1, inc2])

    report = ReportModel(
        id=uuid.uuid4(),
        disaster_id=disaster.id,
        source_type="web",
        raw_payload={"text": "help needed"},
        idempotency_key=f"rep-{uuid.uuid4().hex}",
    )
    session.add(report)

    # Link report to inc1
    rep_link = IncidentReportModel(
        incident_id=inc1.id,
        report_id=report.id,
        relationship="direct",
        linked_by="unit_test",
    )
    session.add(rep_link)
    session.commit()

    return disaster, inc1, inc2, report


class TestIncidentReviewService:
    def test_verify_incident_updates_status_and_records_audit(
        self,
        review_service_with_db: tuple[IncidentReviewService, InMemoryAuditRepository, sessionmaker[Session]],
    ) -> None:
        service, audit_repo, session_factory = review_service_with_db
        with session_factory() as session:
            _, inc1, _, _ = _seed_disaster_and_incidents(session)
            inc1_id = inc1.id

        dispatcher_id = uuid.uuid4()
        result = service.verify_incident(
            incident_id=inc1_id,
            dispatcher_id=dispatcher_id,
            status=IncidentStatus.VERIFIED,
            notes="Confirmed via phone call with village elder",
            operational_priority=PriorityLevel.URGENT,
        )

        assert result.incident_id == inc1_id
        assert result.status == IncidentStatus.VERIFIED
        assert result.operational_priority == PriorityLevel.URGENT
        assert result.verified_by == dispatcher_id

        # Verify DB updated
        with session_factory() as session:
            updated = session.get(IncidentModel, inc1_id)
            assert updated is not None
            assert updated.status == "verified"
            assert updated.operational_priority == "urgent"
            assert updated.last_confirmed_at is not None
            assert updated.severity_facts.get("verification_notes") == "Confirmed via phone call with village elder"

        # Verify audit event
        assert len(audit_repo.events) == 1
        audit = audit_repo.events[0]
        assert audit.action == "incident.verified"
        assert audit.actor_id == dispatcher_id
        assert audit.entity_id == inc1_id

    def test_approve_merge_closes_source_attaches_reports_and_records_audit(
        self,
        review_service_with_db: tuple[IncidentReviewService, InMemoryAuditRepository, sessionmaker[Session]],
    ) -> None:
        service, audit_repo, session_factory = review_service_with_db
        with session_factory() as session:
            _, inc1, inc2, report = _seed_disaster_and_incidents(session)
            inc1_id, inc2_id, rep_id = inc1.id, inc2.id, report.id

        dispatcher_id = uuid.uuid4()
        result = service.review_link(
            source_incident_id=inc1_id,
            target_incident_id=inc2_id,
            action=LinkReviewAction.APPROVE_MERGE,
            dispatcher_id=dispatcher_id,
            reason="Duplicate reports from same household caller",
        )

        assert result.action == "approved"
        assert result.status == "active"
        assert result.source_incident_id == inc1_id
        assert result.target_incident_id == inc2_id
        assert result.reassigned_report_count == 1
        assert result.merge_event_id is not None

        # Verify database state
        with session_factory() as session:
            # 1. Entity merge event exists
            merge_event = session.get(EntityMergeEventModel, result.merge_event_id)
            assert merge_event is not None
            assert merge_event.source_entity_id == inc1_id
            assert merge_event.target_entity_id == inc2_id
            assert merge_event.status == "active"

            # 2. Source incident closed
            source = session.get(IncidentModel, inc1_id)
            assert source is not None
            assert source.status == "closed"
            assert source.severity_facts.get("merged_into") == str(inc2_id)

            # 3. Target incident has corroborating link for report
            target_links = session.scalars(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == inc2_id,
                    IncidentReportModel.report_id == rep_id,
                )
            ).all()
            assert len(target_links) == 1
            assert target_links[0].relationship == "corroborating"

            # 4. Original link on source incident is NOT deleted
            orig_links = session.scalars(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == inc1_id,
                    IncidentReportModel.report_id == rep_id,
                )
            ).all()
            assert len(orig_links) == 1

        # Verify audit event
        assert any(e.action == "incident.merge_approved" for e in audit_repo.events)

    def test_unmerge_reverses_merge_and_restores_incident_state(
        self,
        review_service_with_db: tuple[IncidentReviewService, InMemoryAuditRepository, sessionmaker[Session]],
    ) -> None:
        service, audit_repo, session_factory = review_service_with_db
        with session_factory() as session:
            _, inc1, inc2, report = _seed_disaster_and_incidents(session)
            inc1_id, inc2_id, rep_id = inc1.id, inc2.id, report.id

        dispatcher_id = uuid.uuid4()
        # 1. Merge
        merge_res = service.review_link(
            source_incident_id=inc1_id,
            target_incident_id=inc2_id,
            action=LinkReviewAction.APPROVE_MERGE,
            dispatcher_id=dispatcher_id,
            reason="Initial merge",
        )
        assert merge_res.merge_event_id is not None

        # 2. Reverse / Unmerge
        unmerge_res = service.review_link(
            source_incident_id=inc1_id,
            target_incident_id=inc2_id,
            action=LinkReviewAction.UNMERGE,
            dispatcher_id=dispatcher_id,
            reason="Caller clarified they are a different household 200m away",
            merge_event_id=merge_res.merge_event_id,
        )

        assert unmerge_res.action == "unmerged"
        assert unmerge_res.status == "reversed"
        assert unmerge_res.merge_event_id == merge_res.merge_event_id

        # Verify database state after unmerge
        with session_factory() as session:
            # Merge event reversed
            event = session.get(EntityMergeEventModel, merge_res.merge_event_id)
            assert event is not None
            assert event.status == "reversed"
            assert event.reversed_at is not None
            assert event.reversed_by == dispatcher_id

            # Source incident reopened
            source = session.get(IncidentModel, inc1_id)
            assert source is not None
            assert source.status == "unverified"
            assert "merged_into" not in source.severity_facts

            # Report link removed from target incident
            target_link = session.scalars(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == inc2_id,
                    IncidentReportModel.report_id == rep_id,
                )
            ).first()
            assert target_link is None

            # Original report link on source still intact
            orig_link = session.scalars(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == inc1_id,
                    IncidentReportModel.report_id == rep_id,
                )
            ).first()
            assert orig_link is not None

        # Verify audit event for unmerge
        assert any(e.action == "incident.unmerged" for e in audit_repo.events)

    def test_self_merge_raises_value_error(
        self,
        review_service_with_db: tuple[IncidentReviewService, InMemoryAuditRepository, sessionmaker[Session]],
    ) -> None:
        service, _, session_factory = review_service_with_db
        with session_factory() as session:
            _, inc1, _, _ = _seed_disaster_and_incidents(session)
            inc1_id = inc1.id

        with pytest.raises(ValueError, match="Cannot merge an incident into itself"):
            service.review_link(
                source_incident_id=inc1_id,
                target_incident_id=inc1_id,
                action=LinkReviewAction.APPROVE_MERGE,
                dispatcher_id=uuid.uuid4(),
                reason="Invalid",
            )
