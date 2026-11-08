"""Integration tests for dynamic, adaptive disaster dialogue over IVR API."""
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


class TestAdaptiveDialogueFlow:
    """Verify that the helpline dialogue adapts dynamically to caller information."""

    @pytest.mark.asyncio
    async def test_adaptive_one_shot_intake_and_dispatch(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
        seeded_disaster_id: str,
    ) -> None:
        """If caller provides location, count, and situation in Turn 1, the system does not ask redundant questions."""
        mock_speech = MockSpeechRecognizer()
        mock_tts = MockTTSSynthesizer(sample_rate=16000)
        workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
        )

        app.dependency_overrides[get_speech_recognizer] = lambda: mock_speech
        app.dependency_overrides[get_tts_synthesizer] = lambda: mock_tts
        app.dependency_overrides[get_audio_triage_workflow] = lambda: workflow

        try:
            # 1. Start Call
            start_res = client.post(
                "/api/v1/ivr/calls/start",
                json={
                    "disaster_id": seeded_disaster_id,
                    "caller_phone": "+919876543210",
                    "language_code": "hi",
                },
            )
            assert start_res.status_code == 201
            d_start = start_res.json()
            call_sid = d_start["call_sid"]

            # 2. Turn 1: Comprehensive distress report in a single utterance
            rich_utterance = (
                "Hum Alappuzha Boat Jetty ke pass 6 log chhat par phanse hain, "
                "paani 6 feet badh chuka hai, please jaldi naav bhejo!"
            )
            mock_speech.queue_transcript(rich_utterance, confidence=0.97)

            turn_res = client.post(
                f"/api/v1/ivr/calls/{call_sid}/turn",
                data={"text_override": rich_utterance},
            )
            assert turn_res.status_code == 200
            d_turn = turn_res.json()

            # Dynamic extraction asserts
            assert d_turn["extracted_location"] is not None
            assert "Alappuzha" in d_turn["extracted_location"]
            assert d_turn["extracted_people_count"] == 6
            assert "boat" in d_turn["extracted_needs"]

            # Call completed immediately without asking redundant questions!
            assert d_turn["is_completed"] is True
            assert d_turn["state"] == "completed"
            assert d_turn["report_id"] is not None
            assert d_turn["incident_id"] is not None
            assert d_turn["proposed_resource"] is not None
            assert "Alappuzha" in d_turn["prompt_text"]

            # Inspect session
            status_res = client.get(f"/api/v1/ivr/calls/{call_sid}")
            assert status_res.status_code == 200
            d_status = status_res.json()
            assert d_status["people_count"] == 6
            assert "boat" in d_status["needs"]
        finally:
            app.dependency_overrides.clear()
