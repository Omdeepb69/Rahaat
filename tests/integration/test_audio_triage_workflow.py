"""Integration tests for AutomatedAudioTriageWorkflow (Task 6.5)."""
from __future__ import annotations

import io
import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_audio_triage_workflow, get_session_factory
from raahat.application.events import EventBroadcaster
from raahat.application.resources import ResourceService
from raahat.application.workflow import AutomatedAudioTriageWorkflow, WorkflowResult
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import PriorityLevel, ResourceStatus, ResourceType
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.incident import (
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LandmarkModel
from raahat.infrastructure.database.models.operation import AssignmentModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.repositories.audit import PostgresAuditRepository
from raahat.infrastructure.database.repositories.resource import PostgresResourceRepository
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.speech import AudioInput, MockSpeechRecognizer

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
            name=f"Pune Monsoon Flood {uuid.uuid4().hex[:6]}",
            disaster_type="flood",
            status="active",
        )
        session.add(disaster)
        session.commit()
        session.refresh(disaster)
        return disaster


@pytest.fixture
def seeded_environment(
    session_factory: sessionmaker[Session],
    seeded_disaster: DisasterModel,
) -> tuple[DisasterModel, uuid.UUID, uuid.UUID]:
    """Seed a landmark and a nearby rescue boat."""
    with session_factory() as session:
        # 1. Landmark at Shaniwar Wada, Pune
        landmark_id = uuid.uuid4()
        lm = LandmarkModel(
            id=landmark_id,
            name="Shaniwar Wada",
            location="SRID=4326;POINT(73.8553 18.5196)",
            kind="historical",
            salience=1.0,
            metadata_={"city": "Pune", "ward": "Kasba Peth"},
        )
        session.add(lm)

        # 2. Rescue unit (NDRF motorboat) registered nearby
        audit_repo = PostgresAuditRepository(session_factory)
        resource_repo = PostgresResourceRepository(session_factory)
        resource_service = ResourceService(
            resource_repo=resource_repo,
            audit_repo=audit_repo,
            session_factory=session_factory,
        )

        res = resource_service.register_resource(
            disaster_id=seeded_disaster.id,
            resource_type=ResourceType.BOAT,
            name="NDRF Motorboat Alpha-1",
            capacity=12,
            availability_status=ResourceStatus.AVAILABLE,
            location=PointCoordinates(latitude=18.5205, longitude=73.8560),
            registered_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            session=session,
        )

        session.commit()
        return seeded_disaster, landmark_id, res.id


class TestAutomatedAudioTriageWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_direct_audio_e2e_execution(
        self,
        session_factory: sessionmaker[Session],
        seeded_environment: tuple[DisasterModel, uuid.UUID, uuid.UUID],
        client: TestClient,
    ) -> None:
        disaster, landmark_id, resource_id = seeded_environment

        # Distress message indicating critical P0 life-threatening situation with landmark mention
        mock_text = (
            "Paani 5 feet badh raha hai at Shaniwar Wada. "
            "Two elderly people trapped on ground floor, severe medical emergency, oxygen running out."
        )
        mock_speech = MockSpeechRecognizer(default_text=mock_text, default_confidence=0.98)
        broadcaster = EventBroadcaster()

        workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
            broadcaster=broadcaster,
        )

        # Non-empty audio input simulating distress call
        dummy_audio = b"\x00" * 3200 + b"\x7f\x80" * 800
        audio_input = AudioInput(audio_bytes=dummy_audio, sample_rate=16000)

        result: WorkflowResult = await workflow.run(
            audio_input=audio_input,
            disaster_id=disaster.id,
            caller_info={
                "caller_phone": "+919820011223",
                "language_hint": "hi",
            },
        )

        # 1. Assert WorkflowResult integrity
        assert result.disaster_id == disaster.id
        assert result.transcript == mock_text
        assert result.confidence == 0.98
        assert result.has_speech is True
        assert result.is_new_incident is True
        assert result.priority in (PriorityLevel.CRITICAL_REVIEW, PriorityLevel.URGENT)
        assert len(result.priority_reasons) > 0
        assert result.proposed_resource_id == resource_id
        assert result.proposed_resource_name == "NDRF Motorboat Alpha-1"
        assert result.execution_time_ms > 0

        # 2. Verify Database Persistence
        with session_factory() as session:
            # Report record
            report = session.get(ReportModel, result.report_id)
            assert report is not None
            assert report.processing_status == "extracted"
            assert report.raw_payload["transcript"] == mock_text
            assert report.source_identity == "+919820011223"

            # Incident record
            incident = session.get(IncidentModel, result.incident_id)
            assert incident is not None
            assert incident.operational_priority == result.priority.value
            assert incident.disaster_id == disaster.id

            # Incident report link
            link = session.scalars(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == result.incident_id,
                    IncidentReportModel.report_id == result.report_id,
                )
            ).first()
            assert link is not None

            # Assignment record (status must strictly be PROPOSED)
            assignment = session.scalars(
                select(AssignmentModel).where(
                    AssignmentModel.incident_id == result.incident_id,
                    AssignmentModel.resource_id == resource_id,
                )
            ).first()
            assert assignment is not None
            assert assignment.status == "proposed"

            # Cryptographic audit events
            audit_events = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_id.in_([result.incident_id, assignment.id])
                )
            ).all()
            actions = {e.action for e in audit_events}
            assert "incident.triaged" in actions
            assert "assignment.proposed" in actions

        # 3. Verify Citizen Ticket Tracking Endpoint advances to 'triaged'
        ticket_res = client.get(f"/api/v1/reports/{result.report_id}/ticket")
        assert ticket_res.status_code == 200
        ticket_data = ticket_res.json()
        assert ticket_data["report_id"] == str(result.report_id)
        assert ticket_data["stage"] == "triaged"
        assert ticket_data["priority"] == result.priority.value
        assert any("NDRF Motorboat Alpha-1 (proposed)" in r for r in ticket_data["assigned_resources"])

    @pytest.mark.asyncio
    async def test_workflow_run_for_persisted_report(
        self,
        session_factory: sessionmaker[Session],
        seeded_environment: tuple[DisasterModel, uuid.UUID, uuid.UUID],
        client: TestClient,
    ) -> None:
        disaster, _, resource_id = seeded_environment
        report_id = uuid.uuid4()

        # Insert a pending report into the database
        with session_factory() as session:
            model = ReportModel(
                id=report_id,
                disaster_id=disaster.id,
                source_type="citizen_web_voice",
                source_identity="+919988776655",
                raw_payload={
                    "text": "Water rising rapidly, elderly woman with broken leg trapped on 1st floor",
                    "latitude": 18.5200,
                    "longitude": 73.8550,
                },
                processing_status="extracted",
                idempotency_key=f"rep_{report_id.hex}",
            )
            session.add(model)
            session.commit()

        workflow = AutomatedAudioTriageWorkflow(session_factory=session_factory)
        result = await workflow.run_for_report(report_id=report_id)

        assert result.report_id == report_id
        assert result.disaster_id == disaster.id
        assert result.priority in (PriorityLevel.CRITICAL_REVIEW, PriorityLevel.URGENT)
        assert result.proposed_resource_id == resource_id

        # Verify ticket tracking
        ticket_res = client.get(f"/api/v1/reports/{report_id}/ticket")
        assert ticket_res.status_code == 200
        assert ticket_res.json()["stage"] == "triaged"

    def test_workflow_api_route_multipart_audio(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_environment: tuple[DisasterModel, uuid.UUID, uuid.UUID],
    ) -> None:
        disaster, _, resource_id = seeded_environment

        # Override workflow dependency to use MockSpeechRecognizer
        mock_speech = MockSpeechRecognizer(
            default_text="Flash flood entering houses near river bank, 3 children trapped",
            default_confidence=0.95,
        )
        custom_workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
        )
        app.dependency_overrides[get_audio_triage_workflow] = lambda: custom_workflow

        try:
            fake_audio_bytes = b"\x00\x01\x02\x03" * 256
            files = {
                "audio_file": ("test_distress.wav", io.BytesIO(fake_audio_bytes), "audio/wav")
            }
            data = {
                "disaster_id": str(disaster.id),
                "caller_phone": "+919876500000",
                "latitude": "18.5196",
                "longitude": "73.8553",
            }

            res = client.post("/api/v1/workflow/audio-triage", files=files, data=data)
            assert res.status_code == 200
            body = res.json()
            assert "report_id" in body
            assert "incident_id" in body
            assert body["priority"] in ("critical_review", "urgent")
            assert body["proposed_resource_id"] == str(resource_id)
            assert body["proposed_resource_name"] == "NDRF Motorboat Alpha-1"
            assert body["execution_time_ms"] > 0
        finally:
            app.dependency_overrides.clear()

    def test_workflow_api_route_for_report(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_environment: tuple[DisasterModel, uuid.UUID, uuid.UUID],
    ) -> None:
        disaster, _, resource_id = seeded_environment
        report_id = uuid.uuid4()

        with session_factory() as session:
            model = ReportModel(
                id=report_id,
                disaster_id=disaster.id,
                source_type="web",
                source_identity="+919123456789",
                raw_payload={"text": "Water entered ground floor, need boat immediately"},
                processing_status="extracted",
                idempotency_key=f"rep_{report_id.hex}",
            )
            session.add(model)
            session.commit()

        res = client.post(f"/api/v1/workflow/reports/{report_id}/run")
        assert res.status_code == 200
        body = res.json()
        assert body["report_id"] == str(report_id)
        assert body["proposed_resource_id"] == str(resource_id)

    @pytest.mark.asyncio
    async def test_workflow_in_memory_execution_fallback(self) -> None:
        """Verify AutomatedAudioTriageWorkflow can execute fully in-memory without a database."""
        workflow = AutomatedAudioTriageWorkflow(session_factory=None)
        audio = AudioInput(audio_bytes=b"\x00" * 100, sample_rate=16000)
        disaster_id = uuid.uuid4()

        res = await workflow.run(
            audio_input=audio,
            disaster_id=disaster_id,
            caller_info={"caller_phone": "+919876543210"},
        )
        assert res.report_id is not None
        assert res.incident_id is not None
        assert res.disaster_id == disaster_id
        assert res.priority is not None
