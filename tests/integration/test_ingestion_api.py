"""Integration tests for Report Ingestion API and channels with PostgreSQL."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import create_app
from raahat.api.dependencies import get_db, get_session_factory
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models import (
    DisasterModel,
    OutboxEventModel,
    ReportModel,
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
        yield session


@pytest.fixture
def test_disaster(db_session: Session) -> DisasterModel:
    disaster = DisasterModel(
        name="Ingestion Test Flood 2026",
        disaster_type="flood",
        status="active",
    )
    db_session.add(disaster)
    db_session.commit()
    db_session.refresh(disaster)
    return disaster


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_session_factory() -> sessionmaker[Session]:
        return session_factory

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = override_session_factory

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_submit_report_generic_success(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    idempotency_key = f"generic-{uuid.uuid4().hex}"
    payload = {
        "disaster_id": str(test_disaster.id),
        "source_type": SourceType.WEB.value,
        "source_identity": "+919876543210",
        "channel_reference": "web_portal",
        "raw_payload": {"text": "help stranded", "count": 2},
        "idempotency_key": idempotency_key,
    }

    resp = client.post("/api/v1/reports", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    report_id = uuid.UUID(data["report_id"])
    assert data["is_duplicate"] is False
    assert data["status"] == "pending"
    assert data["idempotency_key"] == idempotency_key

    # Verify report row in DB
    db_session.expire_all()
    saved_report = db_session.get(ReportModel, report_id)
    assert saved_report is not None
    assert saved_report.disaster_id == test_disaster.id
    assert saved_report.source_identity == "+919876543210"
    assert saved_report.raw_payload == {"text": "help stranded", "count": 2}

    # Verify atomic outbox event was created in outbox_events
    outbox_event = (
        db_session.query(OutboxEventModel)
        .filter(
            OutboxEventModel.aggregate_type == "report",
            OutboxEventModel.aggregate_id == report_id,
        )
        .first()
    )
    assert outbox_event is not None
    assert outbox_event.event_type == "raahat.report.received"
    assert outbox_event.status == "pending"
    assert outbox_event.payload["report_id"] == str(report_id)


def test_submit_report_idempotency_returns_200(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    idempotency_key = f"idem-{uuid.uuid4().hex}"
    payload = {
        "disaster_id": str(test_disaster.id),
        "source_type": SourceType.SMS.value,
        "source_identity": "+919111122222",
        "raw_payload": {"sms": "need evacuation"},
        "idempotency_key": idempotency_key,
    }

    # First submission -> 201 Created
    resp1 = client.post("/api/v1/reports", json=payload)
    assert resp1.status_code == 201
    data1 = resp1.json()
    first_report_id = data1["report_id"]
    assert data1["is_duplicate"] is False

    # Second submission with same key -> 200 OK with is_duplicate: True
    resp2 = client.post("/api/v1/reports", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_duplicate"] is True
    assert data2["report_id"] == first_report_id

    # Verify only ONE outbox event was created
    db_session.expire_all()
    outbox_count = (
        db_session.query(OutboxEventModel)
        .filter(
            OutboxEventModel.aggregate_type == "report",
            OutboxEventModel.aggregate_id == uuid.UUID(first_report_id),
        )
        .count()
    )
    assert outbox_count == 1


def test_submit_report_nonexistent_disaster_returns_404(
    client: TestClient,
) -> None:
    fake_disaster_id = uuid.uuid4()
    payload = {
        "disaster_id": str(fake_disaster_id),
        "source_type": SourceType.WEB.value,
        "raw_payload": {"msg": "hello"},
    }

    resp = client.post("/api/v1/reports", json=payload)
    assert resp.status_code == 404
    assert str(fake_disaster_id) in resp.json()["detail"]


def test_submit_via_web_channel_route(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    sub_token = f"web-token-{uuid.uuid4().hex}"
    payload = {
        "disaster_id": str(test_disaster.id),
        "caller_name": "Anita Roy",
        "phone_number": "+919876599999",
        "location_text": "Shiv Temple, Lower Ward",
        "latitude": 15.49,
        "longitude": 73.82,
        "people_count": 3,
        "situation_description": "Water rising rapidly",
        "needs": ["boat", "drinking_water"],
        "submission_token": sub_token,
    }

    resp = client.post("/api/v1/reports/channels/web", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    report_id = uuid.UUID(data["report_id"])
    assert data["idempotency_key"] == f"web-{sub_token}"

    db_session.expire_all()
    saved = db_session.get(ReportModel, report_id)
    assert saved is not None
    assert saved.source_type == "web"
    assert saved.source_identity == "+919876599999"


def test_submit_via_sms_channel_route(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    msg_id = f"SM-{uuid.uuid4().hex[:12]}"
    payload = {
        "disaster_id": str(test_disaster.id),
        "sender": "+919800011122",
        "message": "Trapped on terrace with infant please send help",
        "message_id": msg_id,
        "shortcode": "56161",
    }

    resp = client.post("/api/v1/reports/channels/sms", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    report_id = uuid.UUID(data["report_id"])
    assert data["idempotency_key"] == f"sms-{msg_id}"

    db_session.expire_all()
    saved = db_session.get(ReportModel, report_id)
    assert saved is not None
    assert saved.source_type == "sms"
    assert saved.channel_reference == "56161"


def test_submit_via_radio_channel_route(
    client: TestClient,
    test_disaster: DisasterModel,
    db_session: Session,
) -> None:
    entry_id = f"RADIO-LOG-{uuid.uuid4().hex[:8]}"
    payload = {
        "disaster_id": str(test_disaster.id),
        "operator_callsign": "DISPATCH-ALPHA",
        "frequency_channel": "VHF-CH16",
        "transmission_text": "Medical team urgently requested at relief center",
        "reporting_party": "RESCUE-1",
        "people_count": 8,
        "operator_entry_id": entry_id,
    }

    resp = client.post("/api/v1/reports/channels/radio", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    report_id = uuid.UUID(data["report_id"])
    assert data["idempotency_key"] == f"radio-{entry_id}"

    db_session.expire_all()
    saved = db_session.get(ReportModel, report_id)
    assert saved is not None
    assert saved.source_type == "radio"
    assert saved.source_identity == "DISPATCH-ALPHA"


def test_get_report_by_id(
    client: TestClient,
    test_disaster: DisasterModel,
) -> None:
    create_payload = {
        "disaster_id": str(test_disaster.id),
        "source_type": SourceType.WEB.value,
        "source_identity": "+919000000001",
        "raw_payload": {"info": "detail check"},
    }
    create_resp = client.post("/api/v1/reports", json=create_payload)
    assert create_resp.status_code == 201
    report_id = create_resp.json()["report_id"]

    get_resp = client.get(f"/api/v1/reports/{report_id}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["id"] == report_id
    assert detail["disaster_id"] == str(test_disaster.id)
    assert detail["source_type"] == "web"
    assert detail["source_identity"] == "+919000000001"
    assert detail["processing_status"] == "pending"


def test_get_report_not_found(client: TestClient) -> None:
    random_id = uuid.uuid4()
    resp = client.get(f"/api/v1/reports/{random_id}")
    assert resp.status_code == 404


def test_list_reports_with_filter(
    client: TestClient,
    test_disaster: DisasterModel,
) -> None:
    # First submit a report for this disaster
    client.post(
        "/api/v1/reports",
        json={
            "disaster_id": str(test_disaster.id),
            "source_type": SourceType.WEB.value,
            "raw_payload": {"msg": "list test"},
        },
    )

    # Query reports for test disaster
    resp = client.get(f"/api/v1/reports?disaster_id={test_disaster.id}&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert all(item["disaster_id"] == str(test_disaster.id) for item in data["items"])
