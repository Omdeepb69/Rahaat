"""Integration tests for Task 6.1: API Ergonomics, Query Filtering & SSE Authentication Fallbacks."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_event_broadcaster, get_session_factory
from raahat.application.events import EventBroadcaster
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.incident import IncidentModel
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
def test_broadcaster() -> EventBroadcaster:
    return EventBroadcaster()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    test_broadcaster: EventBroadcaster,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_event_broadcaster] = lambda: test_broadcaster
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_disaster(session_factory: sessionmaker[Session]) -> DisasterModel:
    with session_factory() as session:
        disaster = DisasterModel(
            name=f"Ergonomics Test Disaster {uuid.uuid4().hex[:6]}",
            disaster_type="flood",
            status="active",
        )
        session.add(disaster)
        session.flush()

        incident = IncidentModel(
            disaster_id=disaster.id,
            status="verified",
            operational_priority="urgent",
            severity_facts={"trapped": True},
        )
        session.add(incident)

        resource = ResourceModel(
            disaster_id=disaster.id,
            resource_type="boat",
            name="NDRF Rescue Boat E1",
            availability_status="available",
        )
        session.add(resource)
        session.commit()
        session.refresh(disaster)
        return disaster


class TestApiErgonomics:
    def test_sse_stream_authenticates_via_query_parameter(
        self, client: TestClient, test_broadcaster: EventBroadcaster
    ) -> None:
        dispatcher_id = uuid.uuid4()
        res = client.get(f"/api/v1/events/stream?dispatcher_id={dispatcher_id}&max_events=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert "event: connected" in res.text

    def test_sse_stream_unauthorized_without_dispatcher_credentials(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DEMO_MODE", raising=False)
        res = client.get("/api/v1/events/stream")
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_sse_stream_demo_mode_fallback(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DEMO_MODE", "true")
        res = client.get("/api/v1/events/stream?max_events=1")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")

    def test_list_incidents_without_disaster_id_defaults_to_latest(
        self, client: TestClient, seeded_disaster: DisasterModel
    ) -> None:
        res = client.get("/api/v1/incidents")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert any(item["disaster_id"] == str(seeded_disaster.id) for item in items)

    def test_list_incidents_status_open_filter(
        self, client: TestClient, seeded_disaster: DisasterModel
    ) -> None:
        res = client.get(f"/api/v1/incidents?disaster_id={seeded_disaster.id}&status=open")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert all(item["status"] in ("unverified", "verified", "in_progress") for item in items)

    def test_list_resources_without_disaster_id_defaults_to_latest(
        self, client: TestClient, seeded_disaster: DisasterModel
    ) -> None:
        res = client.get("/api/v1/resources")
        assert res.status_code == 200
        items = res.json()
        assert isinstance(items, list)
        assert len(items) >= 1
        assert any(item["name"] == "NDRF Rescue Boat E1" for item in items)
