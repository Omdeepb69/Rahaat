"""Integration tests for ConservativeIncidentMatcher and IncidentResolutionService against PostgreSQL."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.incident_resolution import (
    ConservativeIncidentMatcher,
    IncidentResolutionService,
    ResolutionDecisionType,
)
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import (
    IncidentLinkType,
    IncidentStatus,
    PriorityLevel,
    ProcessingStatus,
    SourceType,
)
from raahat.infrastructure.database.models import DisasterModel, OutboxEventModel, ReportModel
from raahat.infrastructure.database.models.evidence import EvidenceItemModel, EvidenceSpanModel
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
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
        session.query(IncidentLinkModel).delete()
        session.query(IncidentReportModel).delete()
        session.query(LocationHypothesisModel).delete()
        session.query(IncidentModel).delete()
        session.query(EvidenceSpanModel).delete()
        session.query(EvidenceItemModel).delete()
        session.query(OutboxEventModel).delete()
        session.query(ReportModel).delete()
        session.query(DisasterModel).delete()
        session.commit()
        yield session


@pytest.fixture
def test_disaster(db_session: Session) -> DisasterModel:
    disaster = DisasterModel(
        id=uuid.uuid4(),
        name="Integration Incident Resolution Flood 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()
    db_session.refresh(disaster)
    return disaster


def _make_domain_report(
    db_session: Session,
    disaster_id: uuid.UUID,
    payload: dict,
    source_identity: str | None = None,
    channel_reference: str | None = None,
) -> Report:
    report_id = uuid.uuid4()
    now = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    idempotency_key = f"int-rep-{report_id.hex}"

    model = ReportModel(
        id=report_id,
        disaster_id=disaster_id,
        source_type=SourceType.WEB.value,
        source_identity=source_identity,
        channel_reference=channel_reference,
        raw_payload=payload,
        received_at=now,
        client_created_at=now,
        processing_status=ProcessingStatus.PENDING.value,
        idempotency_key=idempotency_key,
    )
    db_session.add(model)
    db_session.commit()

    return Report(
        id=report_id,
        disaster_id=disaster_id,
        source_type=SourceType.WEB,
        source_identity=source_identity,
        channel_reference=channel_reference,
        raw_payload=payload,
        received_at=now,
        client_created_at=now,
        idempotency_key=idempotency_key,
        processing_status=ProcessingStatus.PENDING,
    )


class TestIncidentResolutionIntegration:
    def test_postgres_matcher_queries_active_incidents(
        self,
        db_session: Session,
        test_disaster: DisasterModel,
    ) -> None:
        # Create an existing incident in DB
        inc_id = uuid.uuid4()
        inc_m = IncidentModel(
            id=inc_id,
            disaster_id=test_disaster.id,
            status=IncidentStatus.UNVERIFIED.value,
            operational_priority=PriorityLevel.UNASSESSED.value,
            severity_facts={},
        )
        db_session.add(inc_m)

        # Location hypothesis in DB
        hyp_m = LocationHypothesisModel(
            id=uuid.uuid4(),
            incident_id=inc_id,
            location="SRID=4326;POINT(73.8500 18.5200)",
            candidate_label="Shiv Mandir",
            verification_status="confirmed",
        )
        db_session.add(hyp_m)

        # Linked report in DB with phone
        r1 = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"people_count": 3},
            source_identity="+919876543210",
        )
        link_m = IncidentReportModel(
            incident_id=inc_id,
            report_id=r1.id,
            relationship="direct",
            linked_by="seed",
        )
        db_session.add(link_m)
        db_session.commit()

        # Incoming report with same phone and close coordinates (25m away)
        incoming_report = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"latitude": 18.5202, "longitude": 73.8501, "people_count": 3},
            source_identity="+919876543210",
        )

        matcher = ConservativeIncidentMatcher()
        candidates = matcher.find_candidates(incoming_report, session=db_session)

        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.incident_id == inc_id
        assert cand.score >= 0.85
        assert cand.spatial_distance_m is not None
        assert cand.spatial_distance_m <= 35.0
        assert not cand.conflicts

    def test_service_auto_links_duplicate_in_postgres(
        self,
        db_session: Session,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
    ) -> None:
        # Create existing incident
        inc_id = uuid.uuid4()
        inc_m = IncidentModel(
            id=inc_id,
            disaster_id=test_disaster.id,
            status=IncidentStatus.UNVERIFIED.value,
            operational_priority=PriorityLevel.UNASSESSED.value,
            severity_facts={},
        )
        db_session.add(inc_m)

        hyp_m = LocationHypothesisModel(
            id=uuid.uuid4(),
            incident_id=inc_id,
            location="SRID=4326;POINT(73.8500 18.5200)",
            candidate_label="pin",
            verification_status="confirmed",
        )
        db_session.add(hyp_m)

        r1 = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"people_count": 4},
            source_identity="+919876543210",
        )
        db_session.add(IncidentReportModel(
            incident_id=inc_id,
            report_id=r1.id,
            relationship="direct",
            linked_by="seed",
        ))
        db_session.commit()

        # Incoming report matching exact phone and close coordinates
        incoming = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"latitude": 18.5201, "longitude": 73.8501, "people_count": 4},
            source_identity="+919876543210",
        )

        service = IncidentResolutionService(session_factory=session_factory)
        result = service.resolve_report(incoming, session=db_session)

        assert result.decision.decision_type == ResolutionDecisionType.AUTO_LINK
        assert result.is_new_incident is False
        assert result.incident_id == inc_id

        # Verify DB has IncidentReportModel linking report to existing incident as duplicate
        db_session.commit()
        db_session.expire_all()

        stmt = select(IncidentReportModel).where(
            IncidentReportModel.report_id == incoming.id,
            IncidentReportModel.incident_id == inc_id,
        )
        saved_link = db_session.scalars(stmt).first()
        assert saved_link is not None
        assert saved_link.relationship == "duplicate"
        assert saved_link.linked_by == "system:conservative_matcher"

    def test_service_ambiguous_match_persists_review_link(
        self,
        db_session: Session,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
    ) -> None:
        # Existing incident with phone A
        inc_id = uuid.uuid4()
        inc_m = IncidentModel(
            id=inc_id,
            disaster_id=test_disaster.id,
            status=IncidentStatus.UNVERIFIED.value,
            operational_priority=PriorityLevel.UNASSESSED.value,
            severity_facts={},
        )
        db_session.add(inc_m)

        hyp_m = LocationHypothesisModel(
            id=uuid.uuid4(),
            incident_id=inc_id,
            location="SRID=4326;POINT(73.8500 18.5200)",
            candidate_label="pin",
            verification_status="confirmed",
        )
        db_session.add(hyp_m)

        r1 = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={},
            source_identity="+911111122222",
        )
        db_session.add(IncidentReportModel(
            incident_id=inc_id,
            report_id=r1.id,
            relationship="direct",
            linked_by="seed",
        ))
        db_session.commit()

        # Incoming report with differing phone, nearby coordinates (120m away)
        incoming = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"latitude": 18.5208, "longitude": 73.8506},
            source_identity="+919876543210",
        )

        service = IncidentResolutionService(session_factory=session_factory)
        result = service.resolve_report(incoming, session=db_session)

        assert result.decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert result.is_new_incident is True
        assert result.incident_id != inc_id
        assert result.link_id is not None

        db_session.commit()
        db_session.expire_all()

        # Confirm new incident exists
        new_inc = db_session.get(IncidentModel, result.incident_id)
        assert new_inc is not None

        # Confirm pending_review IncidentLinkModel exists
        link_m = db_session.get(IncidentLinkModel, result.link_id)
        assert link_m is not None
        assert link_m.incident_a_id == result.incident_id
        assert link_m.incident_b_id == inc_id
        assert link_m.status == "pending_review"

    def test_service_severe_contradiction_persists_conflicting_link(
        self,
        db_session: Session,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
    ) -> None:
        # Existing incident with receded water
        inc_id = uuid.uuid4()
        inc_m = IncidentModel(
            id=inc_id,
            disaster_id=test_disaster.id,
            status=IncidentStatus.UNVERIFIED.value,
            operational_priority=PriorityLevel.UNASSESSED.value,
            severity_facts={},
        )
        db_session.add(inc_m)

        hyp_m = LocationHypothesisModel(
            id=uuid.uuid4(),
            incident_id=inc_id,
            location="SRID=4326;POINT(73.8500 18.5200)",
            candidate_label="pin",
            verification_status="confirmed",
        )
        db_session.add(hyp_m)

        r1 = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"water_level_trend": "receded"},
            source_identity="+919876543210",
        )
        db_session.add(IncidentReportModel(
            incident_id=inc_id,
            report_id=r1.id,
            relationship="direct",
            linked_by="seed",
        ))

        # Persist evidence item for r1 in DB
        ev_repo = PostgresEvidenceRepository(session_factory)
        ev_item = EvidenceItem(
            id=uuid.uuid4(),
            report_id=r1.id,
            subject_type="incident",
            attribute="water_level_trend",
            value="receded",
            spans=(),
        )
        ev_repo.save(item=ev_item, session=db_session)
        db_session.commit()

        # Incoming report with same phone/location but rising water
        incoming = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"latitude": 18.5200, "longitude": 73.8500, "water_level_trend": "rising"},
            source_identity="+919876543210",
        )

        service = IncidentResolutionService(session_factory=session_factory)
        result = service.resolve_report(incoming, session=db_session)

        # Contradiction MUST force REQUIRES_REVIEW and link_type=conflicting
        assert result.decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert result.is_new_incident is True
        assert result.link_id is not None

        db_session.commit()
        db_session.expire_all()

        link_m = db_session.get(IncidentLinkModel, result.link_id)
        assert link_m is not None
        assert link_m.link_type == IncidentLinkType.CONFLICTING.value
        assert link_m.status == "pending_review"

    def test_service_coordinates_creates_location_hypothesis(
        self,
        db_session: Session,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
    ) -> None:
        # Brand new report with coordinates and no candidates
        incoming = _make_domain_report(
            db_session,
            test_disaster.id,
            payload={"latitude": 19.0760, "longitude": 72.8777},
        )

        service = IncidentResolutionService(session_factory=session_factory)
        result = service.resolve_report(incoming, session=db_session)

        assert result.decision.decision_type == ResolutionDecisionType.CREATE_NEW
        assert result.is_new_incident is True

        db_session.commit()
        db_session.expire_all()

        # Verify LocationHypothesisModel was automatically created for new incident
        stmt = select(LocationHypothesisModel).where(
            LocationHypothesisModel.incident_id == result.incident_id,
        )
        hyp = db_session.scalars(stmt).first()
        assert hyp is not None
        assert hyp.candidate_label == "report_initial_pin"
        assert hyp.verification_status == "unverified"
