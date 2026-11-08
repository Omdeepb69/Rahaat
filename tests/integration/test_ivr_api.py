"""Integration tests for Interactive Emergency IVR Voice Call API (Gnani Prisma & Timbre)."""
from __future__ import annotations

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import (
    get_audio_triage_workflow,
    get_session_factory,
    get_speech_recognizer,
    get_tts_synthesizer,
)
from raahat.application.workflow import AutomatedAudioTriageWorkflow
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.speech import MockSpeechRecognizer, MockTTSSynthesizer
from scripts.seed_demo_data import seed

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine(TEST_DB_URL)
    return get_sync_sessionmaker(engine)


@pytest.fixture
def seeded_disaster_id() -> str:
    scenario = seed(TEST_DB_URL)
    return str(scenario["disaster_id"])


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestInteractiveIVRCallAPI:
    @pytest.mark.asyncio
    async def test_full_interactive_voice_call_flow(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_disaster_id: str,
    ) -> None:
        """Test multi-turn interactive emergency voice call from start to completion."""
        mock_speech = MockSpeechRecognizer()
        mock_tts = MockTTSSynthesizer(sample_rate=16000)
        custom_workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
        )

        app.dependency_overrides[get_speech_recognizer] = lambda: mock_speech
        app.dependency_overrides[get_tts_synthesizer] = lambda: mock_tts
        app.dependency_overrides[get_audio_triage_workflow] = lambda: custom_workflow

        try:
            # 1. Start Call
            start_payload = {
                "disaster_id": seeded_disaster_id,
                "caller_phone": "+919820011223",
                "language_code": "hi",
            }
            res_start = client.post("/api/v1/ivr/calls/start", json=start_payload)
            assert res_start.status_code == 201
            d_start = res_start.json()
            call_sid = d_start["call_sid"]
            assert d_start["state"] == "awaiting_location"
            assert "kahan phanse hain" in d_start["prompt_text"].lower()
            assert d_start["prompt_audio_base64"] is not None

            # 2. Turn 1: Caller answers location via text override
            mock_speech.queue_transcript("Shaniwar Wada ke pass", confidence=0.95)
            turn1_res = client.post(
                f"/api/v1/ivr/calls/{call_sid}/turn",
                data={"text_override": "Shaniwar Wada ke pass"},
            )
            assert turn1_res.status_code == 200
            d_turn1 = turn1_res.json()
            assert d_turn1["state"] == "awaiting_people_count"
            assert "kitne log" in d_turn1["prompt_text"].lower()

            # 3. Turn 2: Caller states headcount ("chaar log")
            mock_speech.queue_transcript("Hum chaar log hain", confidence=0.92)
            turn2_res = client.post(
                f"/api/v1/ivr/calls/{call_sid}/turn",
                data={"text_override": "Hum chaar log hain"},
            )
            assert turn2_res.status_code == 200
            d_turn2 = turn2_res.json()
            assert d_turn2["state"] == "awaiting_people_count_readback"
            assert "4 vyakti" in d_turn2["prompt_text"]

            # 4. Turn 3: Caller confirms headcount via DTMF "1"
            turn3_res = client.post(
                f"/api/v1/ivr/calls/{call_sid}/turn",
                data={"dtmf_digits": "1"},
            )
            assert turn3_res.status_code == 200
            d_turn3 = turn3_res.json()
            assert d_turn3["state"] == "awaiting_needs"
            assert "madad" in d_turn3["prompt_text"].lower()

            # 5. Turn 4: Caller states needs ("Paani 5 feet badh raha hai, boat aur doctor chahiye")
            mock_speech.queue_transcript(
                "Paani 5 feet badh raha hai, elderly person trapped, boat aur medical team bhejo",
                confidence=0.96,
            )
            turn4_res = client.post(
                f"/api/v1/ivr/calls/{call_sid}/turn",
                data={
                    "text_override": (
                        "Paani 5 feet badh raha hai, elderly person trapped, boat aur medical team bhejo"
                    )
                },
            )
            assert turn4_res.status_code == 200
            d_turn4 = turn4_res.json()
            assert d_turn4["state"] == "completed"
            assert d_turn4["is_completed"] is True
            assert d_turn4["report_id"] is not None
            assert d_turn4["incident_id"] is not None
            assert d_turn4["priority"] in ("critical_review", "urgent", "standard")
            assert d_turn4["proposed_resource"] is not None

            # 6. Verify Call Status Inspection
            status_res = client.get(f"/api/v1/ivr/calls/{call_sid}")
            assert status_res.status_code == 200
            d_status = status_res.json()
            assert d_status["call_sid"] == call_sid
            assert d_status["people_count"] == 4
            assert d_status["people_count_confirmed"] is True
            assert "boat" in d_status["needs"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_voice_audio_turn_execution(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_disaster_id: str,
    ) -> None:
        """Verify uploading an audio file via multipart executes speech transcription."""
        mock_speech = MockSpeechRecognizer()
        mock_tts = MockTTSSynthesizer(sample_rate=16000)

        app.dependency_overrides[get_speech_recognizer] = lambda: mock_speech
        app.dependency_overrides[get_tts_synthesizer] = lambda: mock_tts

        try:
            start_res = client.post(
                "/api/v1/ivr/calls/start",
                json={"disaster_id": seeded_disaster_id, "caller_phone": "+919876543210"},
            )
            assert start_res.status_code == 201
            call_sid = start_res.json()["call_sid"]

            mock_speech.queue_transcript("Bund Garden bridge near Pune station", confidence=0.94)
            audio_bytes = b"\x00" * 3200 + b"\x7f\x80" * 800
            files = {"audio_file": ("caller_voice.wav", audio_bytes, "audio/wav")}

            turn_res = client.post(f"/api/v1/ivr/calls/{call_sid}/turn", files=files)
            assert turn_res.status_code == 200
            data = turn_res.json()
            assert data["state"] == "awaiting_people_count"
            assert data["caller_transcript"] == "Bund Garden bridge near Pune station"
            assert data["prompt_audio_base64"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_call_turn_not_found(self, client: TestClient) -> None:
        res = client.post("/api/v1/ivr/calls/NONEXISTENT-CALL/turn", data={"text_override": "hello"})
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
