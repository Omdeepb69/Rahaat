"""Integration tests for Kerala 2018 Demo scenario and API endpoint (Task 6.6)."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_audio_triage_workflow, get_session_factory
from raahat.application.workflow import AutomatedAudioTriageWorkflow
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.speech import MockSpeechRecognizer
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
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestDemoScenario:
    def test_seed_demo_data_execution(self) -> None:
        """Verify seed_demo_data runs and is idempotent."""
        scenario1 = seed(TEST_DB_URL)
        assert "disaster_id" in scenario1
        assert scenario1["disaster_name"] == "Kerala Floods 2018 — Raahat Demo"

        # Re-run to verify idempotency
        scenario2 = seed(TEST_DB_URL)
        assert scenario2["disaster_id"] == scenario1["disaster_id"]

    def test_run_scenario_endpoint(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Verify POST /api/v1/demo/run-scenario executes an audio triage step."""
        scenario = seed(TEST_DB_URL)
        disaster_id = uuid.UUID(scenario["disaster_id"])

        mock_speech = MockSpeechRecognizer(
            default_text="Vellam kerunnu, Alappuzha boat jetty aduth aalkkaar ottappettu, rakshikkaan aal venam",
            default_confidence=0.94,
        )
        custom_workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
        )
        app.dependency_overrides[get_audio_triage_workflow] = lambda: custom_workflow

        try:
            payload = {
                "disaster_id": str(disaster_id),
                "audio_index": 0,
                "latitude": 9.4981,
                "longitude": 76.3388,
                "language_hint": "ml",
            }
            res = client.post("/api/v1/demo/run-scenario", json=payload)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

            data = res.json()
            assert data["disaster_id"] == str(disaster_id)
            assert "report_id" in data
            assert "incident_id" in data
            assert data["priority"] in ("critical_review", "urgent", "standard", "low")
            assert data["execution_time_ms"] > 0
            if data["proposed_resource_id"]:
                assert "NDRF Boat Kerala-01" in (data["proposed_resource_name"] or "")
        finally:
            app.dependency_overrides.clear()

    def test_run_scenario_wraps_audio_index(
        self,
        client: TestClient,
        session_factory: sessionmaker[Session],
    ) -> None:
        """Verify audio_index wraps around modulo number of files."""
        scenario = seed(TEST_DB_URL)
        disaster_id = uuid.UUID(scenario["disaster_id"])

        mock_speech = MockSpeechRecognizer(
            default_text="Hospital area flooded, emergency rescue needed",
            default_confidence=0.90,
        )
        custom_workflow = AutomatedAudioTriageWorkflow(
            session_factory=session_factory,
            speech_recognizer=mock_speech,
        )
        app.dependency_overrides[get_audio_triage_workflow] = lambda: custom_workflow

        try:
            payload = {
                "disaster_id": str(disaster_id),
                "audio_index": 999,
                "latitude": 9.9816,
                "longitude": 76.2999,
            }
            res = client.post("/api/v1/demo/run-scenario", json=payload)
            assert res.status_code == 200
            data = res.json()
            assert data["disaster_id"] == str(disaster_id)
            assert data["proposed_resource_name"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_run_scenario_missing_audio_dir(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify 503 response when demo audio files are not found."""
        monkeypatch.setenv("DEMO_AUDIO_DIR", "/tmp/nonexistent_demo_audio_dir_12345")
        scenario = seed(TEST_DB_URL)

        payload = {
            "disaster_id": scenario["disaster_id"],
            "audio_index": 0,
        }
        res = client.post("/api/v1/demo/run-scenario", json=payload)
        assert res.status_code == 503
        assert "Kerala 2018 audio files not found" in res.json()["detail"]
