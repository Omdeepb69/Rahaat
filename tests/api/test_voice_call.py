"""The guided voice call: language detection, skipping answered questions, routing to the district."""
from __future__ import annotations

import io
import wave
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from raahat.config import get_settings
from raahat.infrastructure.providers.base import ProviderError
from raahat.infrastructure.providers.gnani_prisma import Transcription

KERALA, ERNAKULAM = "32", "555"


def _wav(seconds: float = 0.5) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x01\x00" * int(16000 * seconds))
    return buffer.getvalue()


class FakeSpeech:
    def __init__(self) -> None:
        self.replies: list[tuple[str, str | None]] = []
        self.hints: list[str | None] = []
        self.fail = False

    def transcribe(self, audio: bytes, *, language_hint: str | None = None, sample_rate: int = 16000) -> Transcription:
        self.hints.append(language_hint)
        if self.fail:
            raise ProviderError("gnani_prisma", "unavailable")
        said, language = self.replies.pop(0)
        return Transcription(text=said, language=language, confidence=None, provider="fake",
                             model="fake", duration_ms=1.0)


class FakeVoice:
    configured = True

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str]] = []

    def synthesize(self, text_value: str, *, language: str) -> bytes:
        self.spoken.append((language, text_value))
        return _wav(0.1)


@pytest.fixture()
def caller(monkeypatch, db, tmp_path) -> Iterator[tuple[TestClient, FakeSpeech, FakeVoice]]:
    from raahat.api.app import create_app
    from raahat.api.routes import voice

    speech, spoken = FakeSpeech(), FakeVoice()
    monkeypatch.setattr(voice, "providers", lambda: SimpleNamespace(speech=speech, voice=spoken))
    monkeypatch.setenv("PUBLIC_INTAKE_ENABLED", "true")
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    with TestClient(create_app(get_settings())) as client:
        yield client, speech, spoken
    get_settings.cache_clear()


def _start(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/public/calls", json={"state_code": KERALA, "district_code": ERNAKULAM})
    assert response.status_code == 201, response.text
    return response.json()


def _say(client: TestClient, call: dict[str, Any], step: str, *, typed: str | None = None,
         audio: bytes | None = None, token: str | None = None) -> Any:
    files = {"audio": ("answer.wav", audio, "audio/wav")} if audio else None
    data = {"step": step, **({"text": typed} if typed else {})}
    return client.post(
        f"/api/v1/public/calls/{call['call_id']}/turns", data=data, files=files,
        headers={"X-Call-Token": token or call["token"]},
    )


def test_spoken_malayalam_call_becomes_a_report_for_the_district(caller, db) -> None:
    client, speech, _ = caller
    call = _start(client)
    assert call["step"] == "situation"
    assert [line["language"] for line in call["prompt"]] == ["hi", "en"]
    assert call["district"] == "Ernakulam" and call["language"] == "hi"

    speech.replies.append(("ഞങ്ങളുടെ വീട്ടിൽ വെള്ളം കയറി 5 പേർ ടെറസിൽ കുടുങ്ങിയിരിക്കുകയാണ്", "ml-IN"))
    first = _say(client, call, "situation", audio=_wav())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["language"] == "ml" and body["language_source"] == "detected"
    assert body["facts"]["people_count"] == 5 and body["facts"]["trapped"] is True
    assert body["step"] == "location"
    assert body["prompt"][0]["language"] == "ml"
    assert speech.hints == [None]

    body = _say(client, call, "location", typed="ആലുവ ബസ് സ്റ്റാൻഡിന് അടുത്ത്").json()
    assert body["step"] == "callback", "people and safety were already answered"
    body = _say(client, call, "callback", typed="98765 43210").json()
    assert body["facts"]["phone"] == "9876543210"
    assert body["step"] == "name"
    body = _say(client, call, "name", typed="Ravi").json()
    assert body["done"] is True and body["step"] == "done"
    ticket = body["ticket"]
    assert ticket

    with db() as session:
        row = session.execute(text(
            "SELECT r.raw_payload, r.language_code, r.source_type, d.state_code, d.district_code, d.is_standing "
            "FROM reports r JOIN disasters d ON d.id = r.disaster_id WHERE r.id = :id"
        ), {"id": ticket}).one()
    payload = row.raw_payload
    assert (row.state_code, row.district_code, row.is_standing) == (KERALA, ERNAKULAM, True)
    assert row.language_code == "ml" and row.source_type == "web"
    assert payload["people_count"] == 5 and payload["phone_number"] == "9876543210"
    assert payload["caller_name"] == "Ravi"
    assert "കുടുങ്ങിയിരിക്കുകയാണ്" in payload["situation_description"]
    assert [t["step"] for t in payload["voice_call"]["transcript"]] == ["situation", "location", "callback", "name"]
    assert payload["audio"]["content_type"] == "audio/wav"

    again = _say(client, call, "name", typed="Ravi")
    assert again.status_code == 409


def test_unrecognised_language_falls_back_to_hindi(caller) -> None:
    client, speech, _ = caller
    call = _start(client)
    speech.replies.append(("ପାଣି ଘର ଭିତରକୁ ପଶିଲାଣି", "or-IN"))
    body = _say(client, call, "situation", audio=_wav()).json()
    assert body["language"] == "hi"
    assert body["prompt"][0]["language"] == "hi"


def test_silence_is_asked_again_once_then_moves_on(caller) -> None:
    client, speech, _ = caller
    call = _start(client)
    speech.replies.extend([("", None), ("", None)])
    body = _say(client, call, "situation", audio=_wav()).json()
    assert body["step"] == "situation" and body["prompt"][0]["key"] == "retry"
    body = _say(client, call, "situation", audio=_wav()).json()
    assert body["step"] == "location"


def test_failed_transcription_keeps_the_call_going(caller) -> None:
    client, speech, _ = caller
    call = _start(client)
    speech.fail = True
    body = _say(client, call, "situation", audio=_wav()).json()
    assert body["speech_failed"] is True
    assert body["step"] == "situation"


def test_chosen_language_is_used_as_a_hint(caller) -> None:
    client, speech, _ = caller
    call = _start(client)
    chosen = client.post(f"/api/v1/public/calls/{call['call_id']}/language",
                         json={"language": "ta"}, headers={"X-Call-Token": call["token"]})
    assert chosen.json()["language"] == "ta"
    speech.replies.append(("வீட்டில் தண்ணீர் புகுந்துவிட்டது", "ta-IN"))
    _say(client, call, "situation", audio=_wav())
    assert speech.hints == ["ta"]


def test_send_early_and_token_checks(caller, db) -> None:
    client, _, _ = caller
    call = _start(client)
    assert _say(client, call, "situation", typed="Flood", token="wrong").status_code == 404
    assert _say(client, call, "location", typed="Aluva").status_code == 409
    _say(client, call, "situation", typed="Landslide behind the school, two houses buried")
    put = client.put(f"/api/v1/public/calls/{call['call_id']}/position",
                     json={"latitude": 10.1076, "longitude": 76.3516, "accuracy_m": 12},
                     headers={"X-Call-Token": call["token"]})
    assert put.status_code == 200
    sent = client.post(f"/api/v1/public/calls/{call['call_id']}/finish",
                       params={"token": call["token"], "reason": "caller_left"})
    assert sent.status_code == 200 and sent.json()["ticket"]
    with db() as session:
        payload = session.execute(text("SELECT raw_payload FROM reports WHERE id = :id"),
                                  {"id": sent.json()["ticket"]}).scalar_one()
    assert payload["latitude"] == 10.1076 and payload["voice_call"]["ended"] == "caller_left"


def test_empty_call_is_not_a_report(caller, db) -> None:
    client, _, _ = caller
    call = _start(client)
    sent = client.post(f"/api/v1/public/calls/{call['call_id']}/finish",
                       headers={"X-Call-Token": call["token"]})
    assert sent.json()["ticket"] is None
    with db() as session:
        assert session.execute(text("SELECT count(*) FROM reports")).scalar_one() == 0


def test_reports_reach_the_existing_district_operation(caller, admin, app) -> None:
    client, _, _ = caller
    operation = app.post("/api/v1/disasters", headers=admin, json={
        "name": "Periyar flood", "disaster_type": "flood", "state_code": KERALA, "district_code": ERNAKULAM,
    }).json()
    call = _start(client)
    _say(client, call, "situation", typed="Water rising near Aluva temple")
    ticket = client.post(f"/api/v1/public/calls/{call['call_id']}/finish",
                         headers={"X-Call-Token": call["token"]}).json()["ticket"]
    report = app.get(f"/api/v1/reports/{ticket}", headers=admin).json()
    assert report["disaster_id"] == operation["id"]


def test_prompt_audio(caller) -> None:
    client, _, voice = caller
    response = client.get("/api/v1/public/voice/ml/location.wav")
    assert response.status_code == 200 and response.content.startswith(b"RIFF")
    assert voice.spoken[-1][0] == "ml"
    done = client.get("/api/v1/public/voice/hi/done.wav")
    assert done.status_code == 200
    assert "एक एक दो" in voice.spoken[-1][1]
    assert client.get("/api/v1/public/voice/xx/location.wav").status_code == 404
    assert client.get("/api/v1/public/voice/ml/greeting.wav").status_code == 404
