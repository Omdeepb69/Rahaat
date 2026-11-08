"""Integration and verification tests for AudioReportProcessor & Speech Pipeline (Task 6.4)."""
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
from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.outbox import OutboxEventModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.speech import MockSpeechRecognizer
from raahat.workers.report_processor import AudioReportProcessor, AudioReportProcessorConfig

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
            name=f"Audio Processor Test Disaster {uuid.uuid4().hex[:6]}",
            disaster_type="flood",
            status="active",
        )
        session.add(disaster)
        session.commit()
        session.refresh(disaster)
        return disaster


class TestAudioReportProcessor:
    @pytest.mark.asyncio
    async def test_audio_distress_upload_to_extracted_lifecycle(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_disaster: DisasterModel,
    ) -> None:
        """Verify: Upload voice distress audio -> Worker processes -> status transitions to 'extracted' -> ticket stage advances."""
        # 1. Citizen submits voice report via API
        transcript_content = "Help! 4 people trapped on roof near Bund Garden bridge Pune water rising fast"
        audio_stream = io.BytesIO(transcript_content.encode("utf-8"))
        files = {
            "audio": ("sos_recording.wav", audio_stream, "audio/wav"),
        }
        data = {
            "disaster_id": str(seeded_disaster.id),
            "caller_name": "Ramesh Shinde",
            "phone_number": "+91-9876543210",
            "location_text": "Near Bund Garden bridge, Pune",
            "situation_description": "Water reached 2nd floor, urgent rescue needed",
            "needs": '["trapped_rescue", "boat_required"]',
        }

        res = client.post("/api/v1/reports/channels/web/voice", files=files, data=data)
        assert res.status_code == 201
        report_id = uuid.UUID(res.json()["report_id"])

        # 2. Verify initial ticket status is 'received'
        ticket_before = client.get(f"/api/v1/reports/{report_id}/ticket").json()
        assert ticket_before["stage"] == "received"
        assert ticket_before["processing_status"] == "pending"

        # 3. Instantiate and run AudioReportProcessor
        recognizer = MockSpeechRecognizer(default_text=transcript_content, default_confidence=0.92)
        processor = AudioReportProcessor(
            session_factory=session_factory,
            speech_recognizer=recognizer,
            config=AudioReportProcessorConfig(batch_size=5),
        )

        processed_count = await processor.run_once()
        assert processed_count >= 1

        # 4. Verify report record in database is extracted and has transcript
        with session_factory() as session:
            report = session.get(ReportModel, report_id)
            assert report is not None
            assert report.processing_status == "extracted"
            assert "transcript" in report.raw_payload
            assert "Bund Garden" in report.raw_payload["transcript"]
            assert report.raw_payload["transcript_confidence"] >= 0.8
            assert "speech_processed_at" in report.raw_payload

            # Verify transactional outbox event
            outbox_stmt = select(OutboxEventModel).where(
                OutboxEventModel.aggregate_id == report_id,
                OutboxEventModel.event_type == "report.extracted",
            )
            outbox_event = session.scalars(outbox_stmt).first()
            assert outbox_event is not None
            assert outbox_event.payload["report_id"] == str(report_id)

        # 5. Verify citizen ticket tracker stage has progressed to 'processing'
        ticket_after = client.get(f"/api/v1/reports/{report_id}/ticket").json()
        assert ticket_after["stage"] == "processing"
        assert ticket_after["processing_status"] == "extracted"

    @pytest.mark.asyncio
    async def test_text_report_processing(
        self,
        session_factory: sessionmaker[Session],
        seeded_disaster: DisasterModel,
    ) -> None:
        """Verify reports without audio (e.g. SMS) transition cleanly to 'extracted'."""
        with session_factory() as session:
            report = ReportModel(
                disaster_id=seeded_disaster.id,
                source_type="sms",
                raw_payload={"text": "Flood water entering ground floor in Karve Nagar"},
                idempotency_key=f"text-test-{uuid.uuid4()}",
                processing_status="pending",
            )
            session.add(report)
            session.commit()
            report_id = report.id

        processor = AudioReportProcessor(session_factory=session_factory)
        success = await processor.process_report(report_id)
        assert success is True

        with session_factory() as session:
            updated = session.get(ReportModel, report_id)
            assert updated is not None
            assert updated.processing_status == "extracted"
            assert updated.raw_payload["text"] == "Flood water entering ground floor in Karve Nagar"
