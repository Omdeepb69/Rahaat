"""Integration tests for PostgresEvidenceRepository and EvidenceGraphService against PostgreSQL."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.evidence import EvidenceGraphService
from raahat.domain.evidence.evidence import EvidenceItem, EvidenceSpan
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import ProcessingStatus, SourceType, VerificationStatus
from raahat.infrastructure.database.models import DisasterModel, OutboxEventModel, ReportModel
from raahat.infrastructure.database.models.evidence import EvidenceItemModel, EvidenceSpanModel
from raahat.infrastructure.database.repositories import PostgresEvidenceRepository
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
        name="Integration Evidence Test Flood 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()
    db_session.refresh(disaster)
    return disaster


@pytest.fixture
def test_report(db_session: Session, test_disaster: DisasterModel) -> ReportModel:
    report = ReportModel(
        id=uuid.uuid4(),
        disaster_id=test_disaster.id,
        source_type="web",
        raw_payload={"people_count": 5, "water_level_trend": "rising", "medical_emergency": True},
        received_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
        processing_status="pending",
        idempotency_key=f"integ-evidence-{uuid.uuid4().hex}",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


def _make_evidence_item(report_id: uuid.UUID, attribute: str, value: object) -> EvidenceItem:
    return EvidenceItem(
        report_id=report_id,
        subject_type="household",
        attribute=attribute,
        value=value,
        observed_at=datetime(2026, 8, 15, 11, 55, tzinfo=timezone.utc),
        verification_status=VerificationStatus.UNVERIFIED,
        spans=(
            EvidenceSpan(
                start_ms=1200,
                end_ms=3400,
                text=f"test span for {attribute}",
                reference={"source_field": attribute},
            ),
        ),
    )


class TestPostgresEvidenceRepository:
    def test_save_and_retrieve_by_id(
        self,
        session_factory: sessionmaker[Session],
        test_report: ReportModel,
        db_session: Session,
    ) -> None:
        repo = PostgresEvidenceRepository(session_factory)
        item = _make_evidence_item(test_report.id, "people_count", 5)

        saved = repo.save(item)

        db_session.expire_all()
        retrieved = repo.get_by_id(saved.id)
        assert retrieved is not None
        assert retrieved.report_id == test_report.id
        assert retrieved.attribute == "people_count"
        assert retrieved.value == 5
        assert len(retrieved.spans) == 1
        assert retrieved.spans[0].start_ms == 1200
        assert retrieved.spans[0].end_ms == 3400
        assert retrieved.spans[0].reference["source_field"] == "people_count"

    def test_save_all_multiple_items_same_report(
        self,
        session_factory: sessionmaker[Session],
        test_report: ReportModel,
        db_session: Session,
    ) -> None:
        repo = PostgresEvidenceRepository(session_factory)
        items = [
            _make_evidence_item(test_report.id, "people_count", 5),
            _make_evidence_item(test_report.id, "water_level_trend", "rising"),
            _make_evidence_item(test_report.id, "medical_emergency", True),
        ]

        saved = repo.save_all(items)
        assert len(saved) == 3

        db_session.expire_all()
        retrieved = repo.list_by_report_id(test_report.id)
        assert len(retrieved) == 3
        attr_set = {it.attribute for it in retrieved}
        assert attr_set == {"people_count", "water_level_trend", "medical_emergency"}

    def test_list_by_attribute(
        self,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        # Create two distinct reports
        r1_model = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="volunteer",
            raw_payload={"water_level_trend": "rising"},
            received_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
            processing_status="pending",
            idempotency_key=f"attr-test-r1-{uuid.uuid4().hex}",
        )
        r2_model = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="sms",
            raw_payload={"water_level_trend": "receded"},
            received_at=datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
            processing_status="pending",
            idempotency_key=f"attr-test-r2-{uuid.uuid4().hex}",
        )
        db_session.add_all([r1_model, r2_model])
        db_session.commit()

        repo = PostgresEvidenceRepository(session_factory)
        items = [
            _make_evidence_item(r1_model.id, "water_level_trend", "rising"),
            _make_evidence_item(r2_model.id, "water_level_trend", "receded"),
            _make_evidence_item(r1_model.id, "people_count", 3),
        ]
        repo.save_all(items)

        db_session.expire_all()
        trend_items = repo.list_by_attribute("water_level_trend")
        assert len(trend_items) == 2
        assert {it.value for it in trend_items} == {"rising", "receded"}

    def test_save_is_idempotent_using_merge(
        self,
        session_factory: sessionmaker[Session],
        test_report: ReportModel,
        db_session: Session,
    ) -> None:
        repo = PostgresEvidenceRepository(session_factory)
        item = _make_evidence_item(test_report.id, "people_count", 5)

        repo.save(item)
        repo.save(item)  # Saving same UUID again should not error or duplicate

        db_session.expire_all()
        retrieved = repo.list_by_report_id(test_report.id)
        assert len(retrieved) == 1


class TestEvidenceGraphServiceIntegration:
    def test_decompose_and_detect_contradictions_in_postgres(
        self,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        # Seed two reports with conflicting claims
        r1_model = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="web",
            raw_payload={"water_level_trend": "rising", "people_count": 4, "medical_emergency": True},
            received_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
            client_created_at=datetime(2026, 8, 15, 11, 55, tzinfo=timezone.utc),
            processing_status="pending",
            idempotency_key=f"graph-r1-{uuid.uuid4().hex}",
        )
        r2_model = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="volunteer",
            raw_payload={"water_level_trend": "receded", "people_count": 10, "medical_emergency": False},
            received_at=datetime(2026, 8, 15, 12, 10, tzinfo=timezone.utc),
            client_created_at=datetime(2026, 8, 15, 12, 5, tzinfo=timezone.utc),
            processing_status="pending",
            idempotency_key=f"graph-r2-{uuid.uuid4().hex}",
        )
        db_session.add_all([r1_model, r2_model])
        db_session.commit()

        repo = PostgresEvidenceRepository(session_factory)
        service = EvidenceGraphService(evidence_repo=repo, session_factory=session_factory)

        r1 = Report(
            id=r1_model.id,
            disaster_id=r1_model.disaster_id,
            source_type=SourceType.WEB,
            raw_payload=r1_model.raw_payload,
            received_at=r1_model.received_at,
            client_created_at=r1_model.client_created_at,
            idempotency_key=r1_model.idempotency_key,
            processing_status=ProcessingStatus.PENDING,
        )
        r2 = Report(
            id=r2_model.id,
            disaster_id=r2_model.disaster_id,
            source_type=SourceType.VOLUNTEER,
            raw_payload=r2_model.raw_payload,
            received_at=r2_model.received_at,
            client_created_at=r2_model.client_created_at,
            idempotency_key=r2_model.idempotency_key,
            processing_status=ProcessingStatus.PENDING,
        )

        service.decompose_report(r1)
        service.decompose_report(r2)

        db_session.expire_all()

        # Confirm items persisted in PostgreSQL
        stored_r1 = repo.list_by_report_id(r1.id)
        stored_r2 = repo.list_by_report_id(r2.id)
        assert len(stored_r1) >= 2
        assert len(stored_r2) >= 2

        # Build evidence graph
        graph = service.build_evidence_graph([r1.id, r2.id])

        assert len(graph.evidence_items) >= 4
        assert set(graph.report_ids) == {r1.id, r2.id}

        # Contradictions detected
        trend_contradictions = [c for c in graph.contradictions if c.attribute == "water_level_trend"]
        assert len(trend_contradictions) == 1
        assert trend_contradictions[0].conflict_type == "trend_conflict"
        assert trend_contradictions[0].severity == "high"

        hc_contradictions = [c for c in graph.contradictions if c.attribute == "people_count"]
        assert len(hc_contradictions) == 1
        assert hc_contradictions[0].conflict_type == "headcount_divergence"

        bool_contradictions = [c for c in graph.contradictions if c.attribute == "medical_emergency"]
        assert len(bool_contradictions) == 1
        assert bool_contradictions[0].conflict_type == "boolean_conflict"

    def test_provenance_resolution_via_postgres_lookup(
        self,
        session_factory: sessionmaker[Session],
        test_disaster: DisasterModel,
        db_session: Session,
    ) -> None:
        r_model = ReportModel(
            id=uuid.uuid4(),
            disaster_id=test_disaster.id,
            source_type="ivr",
            source_identity="Caller-123",
            raw_payload={"headcount": 2, "trapped": True},
            received_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
            client_created_at=datetime(2026, 8, 15, 11, 50, tzinfo=timezone.utc),
            processing_status="pending",
            idempotency_key=f"prov-test-{uuid.uuid4().hex}",
        )
        db_session.add(r_model)
        db_session.commit()

        r = Report(
            id=r_model.id,
            disaster_id=r_model.disaster_id,
            source_type=SourceType.IVR,
            source_identity="Caller-123",
            raw_payload=r_model.raw_payload,
            received_at=r_model.received_at,
            client_created_at=r_model.client_created_at,
            idempotency_key=r_model.idempotency_key,
            processing_status=ProcessingStatus.PENDING,
        )

        repo = PostgresEvidenceRepository(session_factory)
        service = EvidenceGraphService(evidence_repo=repo, session_factory=session_factory)

        items = service.decompose_report(r)
        hc_item = next(it for it in items if it.attribute == "people_count")

        # Resolve provenance via PostgreSQL report lookup
        provenance = service.get_evidence_provenance(hc_item.id)

        assert provenance is not None
        assert provenance.evidence_id == hc_item.id
        assert provenance.report_id == r.id
        assert provenance.source_type == SourceType.IVR
        assert provenance.source_identity == "Caller-123"
        assert provenance.attribute == "people_count"
        assert len(provenance.spans) >= 1

