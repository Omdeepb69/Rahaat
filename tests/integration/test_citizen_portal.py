"""Integration and verification tests for Citizen Web SOS & Audio Portal (Task 6.2)."""
from __future__ import annotations

import io
import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.incident import IncidentModel, IncidentReportModel
from raahat.infrastructure.database.models.operation import AssignmentModel
from raahat.infrastructure.database.models.report import ReportModel
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
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_disaster(session_factory: sessionmaker[Session]) -> DisasterModel:
    with session_factory() as session:
        disaster = DisasterModel(
            name=f"Citizen Portal Test Disaster {uuid.uuid4().hex[:6]}",
            disaster_type="flood",
            status="active",
        )
        session.add(disaster)
        session.commit()
        session.refresh(disaster)
        return disaster


class TestCitizenPortal:
    def test_citizen_portal_index_html_rendered(self, client: TestClient) -> None:
        """GET /sos/ should render the citizen emergency interface."""
        res = client.get("/sos/")
        assert res.status_code == 200
        html = res.text

        # Branding & Elements
        assert "RAAHAT 2.0 EMERGENCY SOS" in html
        assert "btn-record" in html
        assert "btn-location" in html
        assert "sos-form" in html
        assert "btn-submit" in html

    def test_citizen_portal_static_assets_served(self, client: TestClient) -> None:
        """Verify CSS, SVG, and ES module scripts are properly served."""
        css_res = client.get("/sos/css/sos.css")
        assert css_res.status_code == 200
        assert "--primary-red" in css_res.text

        svg_res = client.get("/sos/favicon.svg")
        assert svg_res.status_code == 200
        assert "<svg" in svg_res.text

        recorder_js = client.get("/sos/src/recorder.js")
        assert recorder_js.status_code == 200
        assert "AudioRecorder" in recorder_js.text

        geo_js = client.get("/sos/src/geolocation.js")
        assert geo_js.status_code == 200
        assert "getLiveLocation" in geo_js.text

        app_js = client.get("/sos/src/sos_app.js")
        assert app_js.status_code == 200
        assert "web/voice" in app_js.text

    def test_citizen_portal_track_html_rendered(self, client: TestClient) -> None:
        """GET /sos/track.html should render the ticket tracking page."""
        res = client.get("/sos/track.html")
        assert res.status_code == 200
        html = res.text

        assert "RAAHAT LIVE RESCUE TRACKER" in html
        assert "ticket-id-display" in html
        assert "status-message" in html
        assert "stepper" in html

    def test_submit_web_voice_report(
        self, client: TestClient, seeded_disaster: DisasterModel
    ) -> None:
        """POST /api/v1/reports/channels/web/voice accepts multipart audio upload."""
        fake_audio = io.BytesIO(b"RIFF....WAVEfmt ....data....fake_audio_stream")
        files = {
            "audio": ("distress_call.wav", fake_audio, "audio/wav"),
        }
        data = {
            "disaster_id": str(seeded_disaster.id),
            "caller_name": "Sunita Patil",
            "phone_number": "+91-9876543299",
            "location_text": "Shivaji Nagar bridge, Pune",
            "latitude": "18.5204",
            "longitude": "73.8567",
            "people_count": "3",
            "situation_description": "Water rising rapidly up to chest height.",
            "needs": '["trapped_rescue", "flood_water"]',
        }

        res = client.post("/api/v1/reports/channels/web/voice", files=files, data=data)
        assert res.status_code == 201
        body = res.json()
        assert "report_id" in body
        assert body["disaster_id"] == str(seeded_disaster.id)
        assert body["status"] == "pending"

        # Verify persisted report
        report_id = uuid.UUID(body["report_id"])
        detail_res = client.get(f"/api/v1/reports/{report_id}")
        assert detail_res.status_code == 200
        report_data = detail_res.json()
        assert report_data["source_type"] == "web"
        assert "audio" in report_data["raw_payload"]
        assert report_data["raw_payload"]["audio"]["filename"] == "distress_call.wav"

    def test_report_ticket_status_lifecycle(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_disaster: DisasterModel,
    ) -> None:
        """Test /api/v1/reports/{id}/ticket transitions across received -> triaged -> dispatched."""
        dispatcher_id = uuid.uuid4()
        with session_factory() as session:
            # 1. Create Report
            report = ReportModel(
                disaster_id=seeded_disaster.id,
                source_type="web",
                raw_payload={"location": "Test Location"},
                idempotency_key=f"ticket-test-{uuid.uuid4()}",
                processing_status="pending",
            )
            session.add(report)
            session.commit()
            report_id = report.id

        # Initial status: received
        ticket_res1 = client.get(f"/api/v1/reports/{report_id}/ticket")
        assert ticket_res1.status_code == 200
        data1 = ticket_res1.json()
        assert data1["stage"] == "received"
        assert data1["incident_id"] is None

        # 2. Link to an Incident (triaged)
        with session_factory() as session:
            incident = IncidentModel(
                disaster_id=seeded_disaster.id,
                status="verified",
                operational_priority="critical_review",
            )
            session.add(incident)
            session.flush()

            link = IncidentReportModel(
                incident_id=incident.id,
                report_id=report_id,
                relationship="primary",
                linked_by="test",
            )
            session.add(link)

            # Create resource and assignment (dispatched)
            resource = ResourceModel(
                disaster_id=seeded_disaster.id,
                resource_type="boat",
                name="NDRF Inflatable Boat 4",
                availability_status="assigned",
            )
            session.add(resource)
            session.flush()

            assignment = AssignmentModel(
                incident_id=incident.id,
                resource_id=resource.id,
                assigned_by=dispatcher_id,
                status="en_route",
            )
            session.add(assignment)
            session.commit()

        # Updated status: dispatched
        ticket_res2 = client.get(f"/api/v1/reports/{report_id}/ticket")
        assert ticket_res2.status_code == 200
        data2 = ticket_res2.json()
        assert data2["stage"] == "dispatched"
        assert data2["priority"] == "critical_review"
        assert any("NDRF Inflatable Boat 4" in unit for unit in data2["assigned_resources"])
        assert "en route" in data2["message"].lower()

