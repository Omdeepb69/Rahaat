"""Integration tests for database migrations and models."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raahat.infrastructure.database.models import (
    AuditEventModel,
    DisasterModel,
    EvidenceItemModel,
    EvidenceSpanModel,
    IncidentModel,
    LocationHypothesisModel,
    OutboxEventModel,
    ReportModel,
)
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def db_session() -> Generator[Session, None, None]:
    engine = create_sync_engine(TEST_DB_URL)
    session_maker = get_sync_sessionmaker(engine)
    with session_maker() as session:
        yield session


def test_disaster_and_report_creation(db_session: Session) -> None:
    disaster = DisasterModel(
        name="Kerala Floods 2026",
        disaster_type="flood",
        status="active",
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(disaster)
    db_session.commit()

    report = ReportModel(
        disaster_id=disaster.id,
        source_type="ivr",
        source_identity="+919876543210",
        raw_payload={"transcript": "paani bhar gaya hai shiv mandir ke paas"},
        idempotency_key=f"call-{uuid.uuid4().hex}",
    )
    db_session.add(report)
    db_session.commit()

    saved_report = db_session.get(ReportModel, report.id)
    assert saved_report is not None
    assert saved_report.disaster_id == disaster.id
    assert saved_report.source_identity == "+919876543210"
    assert saved_report.processing_status == "pending"


def test_report_idempotency_constraint(db_session: Session) -> None:
    disaster = DisasterModel(
        name="Assam Floods 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()

    idempotency_key = f"fixed-key-{uuid.uuid4().hex}"
    r1 = ReportModel(
        disaster_id=disaster.id,
        source_type="web",
        raw_payload={"msg": "SOS 1"},
        idempotency_key=idempotency_key,
    )
    db_session.add(r1)
    db_session.commit()

    r2 = ReportModel(
        disaster_id=disaster.id,
        source_type="web",
        raw_payload={"msg": "SOS 2 duplicate"},
        idempotency_key=idempotency_key,
    )
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_location_hypothesis_with_postgis(db_session: Session) -> None:
    disaster = DisasterModel(name="Urban Waterlogging", disaster_type="flood")
    db_session.add(disaster)
    db_session.commit()

    incident = IncidentModel(
        disaster_id=disaster.id,
        status="unverified",
        operational_priority="critical_review",
        severity_facts={"water_level": "first_floor"},
    )
    db_session.add(incident)
    db_session.commit()

    point = WKTElement("POINT(73.95 15.40)", srid=4326)
    hypothesis = LocationHypothesisModel(
        incident_id=incident.id,
        location=point,
        candidate_label="Shiv Mandir",
        probability=0.85,
        uncertainty_radius_m=150.0,
        verification_status="candidate",
    )
    db_session.add(hypothesis)
    db_session.commit()

    saved = db_session.get(LocationHypothesisModel, hypothesis.id)
    assert saved is not None
    assert saved.probability == 0.85
    assert saved.candidate_label == "Shiv Mandir"


def test_location_probability_range_constraint(db_session: Session) -> None:
    disaster = DisasterModel(name="Test Disaster", disaster_type="cyclone")
    db_session.add(disaster)
    db_session.commit()

    incident = IncidentModel(disaster_id=disaster.id)
    db_session.add(incident)
    db_session.commit()

    point = WKTElement("POINT(73.95 15.40)", srid=4326)
    invalid_hyp = LocationHypothesisModel(
        incident_id=incident.id,
        location=point,
        probability=1.5,  # Violates [0, 1]
    )
    db_session.add(invalid_hyp)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_evidence_and_spans(db_session: Session) -> None:
    disaster = DisasterModel(name="Test Disaster Evidence", disaster_type="flood")
    db_session.add(disaster)
    db_session.commit()

    report = ReportModel(
        disaster_id=disaster.id,
        source_type="sms",
        raw_payload={"text": "3 adults trapped on roof"},
        idempotency_key=uuid.uuid4().hex,
    )
    db_session.add(report)
    db_session.commit()

    evidence = EvidenceItemModel(
        report_id=report.id,
        subject_type="incident",
        attribute="people_count",
        value={"count": 3, "location": "roof"},
        confidence=0.95,
        verification_status="unverified",
    )
    db_session.add(evidence)
    db_session.commit()

    span = EvidenceSpanModel(
        evidence_id=evidence.id,
        source_text="3 adults trapped on roof",
        source_start_ms=0,
        source_end_ms=2500,
    )
    db_session.add(span)
    db_session.commit()

    saved_evidence = db_session.get(EvidenceItemModel, evidence.id)
    assert saved_evidence is not None
    assert len(saved_evidence.spans) == 1
    assert saved_evidence.spans[0].source_text == "3 adults trapped on roof"


def test_outbox_event_creation(db_session: Session) -> None:
    event_id = uuid.uuid4()
    outbox = OutboxEventModel(
        aggregate_type="report",
        aggregate_id=event_id,
        event_type="raahat.report.submitted",
        payload={"source": "ivr", "caller": "+919876543210"},
        status="pending",
    )
    db_session.add(outbox)
    db_session.commit()

    saved = db_session.get(OutboxEventModel, outbox.id)
    assert saved is not None
    assert saved.status == "pending"
    assert saved.retry_count == 0
    assert saved.payload["source"] == "ivr"


def test_audit_event_logging(db_session: Session) -> None:
    audit = AuditEventModel(
        action="incident.verified",
        actor_id=uuid.uuid4(),
        entity_type="incident",
        entity_id=uuid.uuid4(),
        prev_hash=None,
        hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        payload={"verified_priority": "urgent"},
    )
    db_session.add(audit)
    db_session.commit()

    saved = db_session.get(AuditEventModel, audit.id)
    assert saved is not None
    assert saved.action == "incident.verified"
    assert saved.hash.startswith("e3b0c442")
