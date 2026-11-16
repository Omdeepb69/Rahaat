"""Report intake, analysis, incident lifecycle and corrections."""
from __future__ import annotations

import uuid

from sqlalchemy import text


def test_operator_report_creates_unverified_incident_with_extracted_facts(app, admin, submit):
    created = submit(
        "Water has entered our house behind the school. We are 6 people, two children. "
        "Water is rising fast.",
        caller_name="Test Caller",
    )
    assert created["is_new_incident"] is True
    assert created["incident_reference"] == "INC-000001"
    incident = app.get(f"/api/v1/incidents/{created['incident_reference']}", headers=admin).json()
    assert incident["status"] == "unverified"
    assert incident["category"] == "flood"
    facts = {f["name"]: f for f in incident["facts"]}
    assert facts["people_count"]["value"] == 6
    assert facts["people_count"]["origin"] == "extracted"
    assert facts["people_count"]["sources"][0]["extractor"] == "rules"
    assert facts["people_count"]["sources"][0]["quote"] == "6 people"
    assert facts["trapped_status"]["known"] is False
    assert "trapped_status" in incident["unknown_fields"]


def test_original_text_is_preserved_verbatim(app, admin, submit):
    original = "ഞങ്ങൾ നാല് പേർ വീട്ടിൽ കുടുങ്ങി, വെള്ളം കയറുന്നു"
    created = submit(original)
    report = app.get(f"/api/v1/reports/{created['report']['id']}", headers=admin).json()
    assert report["original_text"] == original
    assert report["original_language"] == "ml"
    assert report["translated_text"] is None
    stages = {run["stage"] for run in report["processing_runs"]}
    assert {"language_id", "extraction"} <= stages


def test_resubmitting_same_idempotency_key_returns_the_same_report(app, admin, operation):
    body = {"disaster_id": operation, "text": "Help, water rising", "idempotency_key": str(uuid.uuid4())}
    first = app.post("/api/v1/reports", headers=admin, json=body).json()
    second = app.post("/api/v1/reports", headers=admin, json=body).json()
    assert second["already_existed"] is True
    assert second["report"]["id"] == first["report"]["id"]
    assert app.get("/api/v1/reports", headers=admin).json()["total"] == 1


def test_report_without_location_has_no_coordinates(app, admin, submit):
    created = submit("Three people need help, no idea where exactly")
    incident = app.get(f"/api/v1/incidents/{created['incident_id']}", headers=admin).json()
    assert incident["location"]["status"] == "none"
    assert incident["location"]["coordinates"] is None
    assert incident["location_candidates"] == []


def test_closed_operation_rejects_reports(app, admin, operation):
    app.patch(f"/api/v1/disasters/{operation}", headers=admin, json={"status": "closed"})
    response = app.post(
        "/api/v1/reports", headers=admin,
        json={"disaster_id": operation, "text": "help", "idempotency_key": str(uuid.uuid4())},
    )
    assert response.status_code == 409


def test_lifecycle_rejects_invalid_transitions(app, admin, submit):
    incident_id = submit("Flooding near the temple")["incident_id"]
    assert app.post(f"/api/v1/incidents/{incident_id}/status", headers=admin,
                    json={"status": "resolved"}).status_code == 409
    assert app.post(f"/api/v1/incidents/{incident_id}/status", headers=admin,
                    json={"status": "assigned"}).status_code == 409
    verified = app.post(f"/api/v1/incidents/{incident_id}/status", headers=admin, json={"status": "verified"})
    assert verified.status_code == 200
    assert verified.json()["verified_at"] is not None
    no_reason = app.post(f"/api/v1/incidents/{incident_id}/status", headers=admin, json={"status": "closed"})
    assert no_reason.status_code == 409
    closed = app.post(
        f"/api/v1/incidents/{incident_id}/status", headers=admin,
        json={"status": "closed", "closure_reason": "false_report", "note": "Caller confirmed prank"},
    )
    assert closed.status_code == 200


def test_correction_overrides_extraction_and_is_audited(app, admin, submit):
    incident_id = submit("6 people on the roof")["incident_id"]
    corrected = app.patch(
        f"/api/v1/incidents/{incident_id}", headers=admin,
        json={"facts": {"people_count": 9, "trapped_status": True}, "note": "Callback confirmed"},
    ).json()
    facts = {f["name"]: f for f in corrected["facts"]}
    assert facts["people_count"]["value"] == 9
    assert facts["people_count"]["origin"] == "operator"
    # The extracted value is still visible as evidence.
    assert facts["people_count"]["sources"][0]["value"] == 6
    assert corrected["priority"] in ("critical_review", "urgent")
    timeline = app.get(f"/api/v1/incidents/{incident_id}/timeline", headers=admin).json()
    corrections = [e for e in timeline["items"] if e["action"] == "incident.corrected"]
    assert corrections[0]["payload"]["changes"]["people_count"] == {"from": 6, "to": 9}


def test_manual_priority_requires_a_note_and_is_labelled(app, admin, submit):
    incident_id = submit("Need drinking water")["incident_id"]
    assert app.patch(f"/api/v1/incidents/{incident_id}", headers=admin,
                     json={"priority": "urgent"}).status_code == 422
    result = app.patch(f"/api/v1/incidents/{incident_id}", headers=admin,
                       json={"priority": "urgent", "note": "Diabetic resident"}).json()
    assert result["priority"] == "urgent"
    assert result["priority_source"] == "operator"


def test_incident_list_filters_and_counts(app, admin, submit):
    submit("Landslide near the bus stand, 3 people injured")
    submit("Need food for 12 people at the relief camp")
    page = app.get("/api/v1/incidents?category=landslide", headers=admin).json()
    assert page["total"] == 1
    assert app.get("/api/v1/incidents?q=relief", headers=admin).json()["total"] == 1
    counts = app.get("/api/v1/incidents/counts", headers=admin).json()
    assert counts["by_status"]["unverified"] == 2
    assert counts["open_without_location"] == 2


def test_original_report_cannot_be_altered_through_corrections(app, admin, submit, db):
    created = submit("We are 4 people")
    app.patch(f"/api/v1/incidents/{created['incident_id']}", headers=admin, json={"facts": {"people_count": 5}})
    with db() as session:
        stored = session.execute(
            text("SELECT original_text FROM reports WHERE id = :id"), {"id": created["report"]["id"]}
        ).scalar_one()
    assert stored == "We are 4 people"
