"""Event persistence and replay, system status, audit verification, public intake."""
from __future__ import annotations

import json

from raahat.config import get_settings


def _parse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        name, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
        if name:
            events.append((name, data))
    return events


def test_changes_are_persisted_and_replayed_after_a_sequence(app, admin, submit):
    head = app.get("/api/v1/events?after=0", headers=admin).json()["head_seq"]
    submit("Water rising, 2 people trapped")
    page = app.get(f"/api/v1/events?after={head}", headers=admin).json()
    actions = [e["action"] for e in page["items"]]
    assert "report.received" in actions and "incident.created" in actions
    seqs = [e["seq"] for e in page["items"]]
    assert seqs == sorted(seqs)


def test_stream_replays_missed_events_from_last_event_id(app, admin, submit):
    head = app.get("/api/v1/events?after=0", headers=admin).json()["head_seq"]
    submit("First report, flooding")
    submit("Second report, flooding")
    response = app.get(
        "/api/v1/events/stream?max_events=4&max_seconds=5",
        headers={**admin, "Last-Event-ID": str(head)},
    )
    events = _parse(response.text)
    assert events[0][0] == "ready" and events[0][1]["resync"] is False
    replayed = [data["action"] for name, data in events[1:] if name == "change"]
    assert replayed[:2] == ["incident.triaged", "report.received"] or "report.received" in replayed


def test_stream_requests_resync_when_cursor_is_unknown(app, admin):
    response = app.get("/api/v1/events/stream?max_seconds=1", headers={**admin, "Last-Event-ID": "999999"})
    events = _parse(response.text)
    assert events[0][1]["resync"] is True


def test_system_status_reports_real_state(app, admin):
    status = app.get("/api/v1/system/status", headers=admin).json()
    components = {c["key"]: c for c in status["components"]}
    assert components["database"]["status"] == "operational"
    # No worker process runs during API tests: it must not be shown as healthy.
    assert components["worker"]["status"] == "unavailable"
    for key in ("speech", "text_model", "geocoder", "routing", "alerts"):
        assert components[key]["status"] == "not_configured"
    assert status["overall"] == "unavailable"


def test_probe_of_unconfigured_integration_is_refused(app, admin):
    assert app.post("/api/v1/system/integrations/geocoder/probe", headers=admin).status_code == 409


def test_audit_chain_verifies_and_detects_tampering(app, admin, submit, db):
    from sqlalchemy import text

    submit("Flood water entering homes")
    assert app.get("/api/v1/audit/verify", headers=admin).json()["verified"] is True
    with db() as session:
        session.execute(text(
            "UPDATE audit_events SET payload = jsonb_set(payload, '{channel}', '\"tampered\"') "
            "WHERE action = 'report.received'"
        ))
        session.commit()
    result = app.get("/api/v1/audit/verify", headers=admin).json()
    assert result["verified"] is False
    assert result["broken"]


def test_public_intake_is_off_by_default(app):
    assert app.post("/api/v1/public/reports", json={}).status_code == 404


def test_public_intake_when_enabled(monkeypatch, db, operation):
    from fastapi.testclient import TestClient

    from raahat.api.app import create_app

    monkeypatch.setenv("PUBLIC_INTAKE_ENABLED", "true")
    get_settings.cache_clear()
    with TestClient(create_app(get_settings())) as client:
        accepted = client.post("/api/v1/public/reports", json={
            "disaster_id": operation, "situation_description": "Water rising, 3 people on roof",
            "phone_number": "+910000000099",
        })
        assert accepted.status_code == 202
        ticket = accepted.json()["ticket"]
        status = client.get(f"/api/v1/public/tickets/{ticket}").json()
        assert status["stage"] == "received"
        assert "phone" not in json.dumps(status)
    get_settings.cache_clear()
