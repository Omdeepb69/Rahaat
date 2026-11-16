"""Resource register, recommendations and human dispatch decisions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def boat(app, admin, operation):
    body = {"disaster_id": operation, "callsign": "boat-1", "resource_type": "boat",
            "name": "Rescue boat", "capacity": 8}
    created = app.post("/api/v1/resources", headers=admin, json=body).json()
    app.put(f"/api/v1/resources/{created['id']}/position", headers=admin,
            json={"latitude": 10.02, "longitude": 76.30})
    return created


@pytest.fixture()
def ambulance(app, admin, operation):
    body = {"disaster_id": operation, "callsign": "AMB-1", "resource_type": "ambulance",
            "name": "Ambulance", "capacity": 2}
    return app.post("/api/v1/resources", headers=admin, json=body).json()


def _verified(app, admin, submit, text_value: str, **extra) -> str:
    incident_id = submit(text_value, **extra)["incident_id"]
    assert app.post(f"/api/v1/incidents/{incident_id}/status", headers=admin,
                    json={"status": "verified"}).status_code == 200
    return incident_id


def test_resource_registration_validates_and_normalises(app, admin, operation, boat):
    assert boat["callsign"] == "BOAT-1"
    assert boat["status"] == "available"
    assert "water_rescue" in boat["capabilities"]
    duplicate = app.post("/api/v1/resources", headers=admin, json={
        "disaster_id": operation, "callsign": "BOAT-1", "resource_type": "boat", "name": "Another"})
    assert duplicate.status_code == 422
    stored = app.get(f"/api/v1/resources/{boat['id']}", headers=admin).json()
    assert stored["position"]["source"] == "operator"
    assert stored["position"]["reported_at"]


def test_future_position_and_manual_assigned_status_rejected(app, admin, boat):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert app.put(f"/api/v1/resources/{boat['id']}/position", headers=admin,
                   json={"latitude": 10, "longitude": 76, "reported_at": future}).status_code == 422
    assert app.post(f"/api/v1/resources/{boat['id']}/status", headers=admin,
                    json={"status": "assigned"}).status_code == 422
    assert app.post(f"/api/v1/resources/{boat['id']}/status", headers=admin,
                    json={"status": "maintenance"}).status_code == 422  # note required


def test_unverified_incident_cannot_be_dispatched(app, admin, submit, boat):
    incident_id = submit("4 people trapped, water rising")["incident_id"]
    recommendation = app.get(f"/api/v1/dispatch/incidents/{incident_id}/recommendation", headers=admin).json()
    assert recommendation["can_dispatch"] is False
    response = app.post(f"/api/v1/dispatch/incidents/{incident_id}/approve", headers=admin,
                        json={"resource_id": boat["id"]})
    assert response.status_code == 422


def test_recommendation_explains_and_excludes(app, admin, submit, boat, ambulance):
    incident_id = _verified(app, admin, submit, "4 people trapped, water rising",
                            latitude=10.05, longitude=76.32)
    rec = app.get(f"/api/v1/dispatch/incidents/{incident_id}/recommendation", headers=admin).json()
    assert rec["can_dispatch"] is True
    assert [r["capability"] for r in rec["requirements"]] == ["water_rescue"]
    assert rec["candidates"][0]["callsign"] == "BOAT-1"
    assert rec["candidates"][0]["distance_basis"] == "straight_line"
    assert {f["name"] for f in rec["candidates"][0]["factors"]} == {"capability", "proximity", "capacity", "freshness"}
    assert any(e["callsign"] == "AMB-1" for e in rec["excluded"])
    assert any("straight-line" in limit for limit in rec["limitations"])


def test_approval_override_rejection_and_progress(app, admin, submit, boat, ambulance, operation):
    incident_id = _verified(app, admin, submit, "Medical emergency, injured man, need ambulance",
                            latitude=10.05, longitude=76.32)
    rec = app.get(f"/api/v1/dispatch/incidents/{incident_id}/recommendation", headers=admin).json()
    first = rec["candidates"][0]["resource_id"]
    other = next(c["resource_id"] for c in rec["candidates"][1:]) if len(rec["candidates"]) > 1 else None
    if other:
        assert app.post(f"/api/v1/dispatch/incidents/{incident_id}/approve", headers=admin,
                        json={"resource_id": other}).status_code == 422

    decision = app.post(f"/api/v1/dispatch/incidents/{incident_id}/approve", headers=admin,
                        json={"resource_id": first}).json()
    assert decision["followed_recommendation"] is True
    assignment = decision["assignment"]
    assert assignment["stage"] == "approved"
    assert app.get(f"/api/v1/incidents/{incident_id}", headers=admin).json()["status"] == "assigned"
    assert app.get(f"/api/v1/resources/{first}", headers=admin).json()["status"] == "assigned"

    # The same resource cannot be committed twice.
    second_incident = _verified(app, admin, submit, "Another injured person")
    again = app.post(f"/api/v1/dispatch/incidents/{second_incident}/approve", headers=admin,
                     json={"resource_id": first, "reason": "test"})
    assert again.status_code == 409

    progress = app.post(f"/api/v1/dispatch/assignments/{assignment['id']}/progress", headers=admin,
                        json={"stage": "on_scene"}).json()
    assert progress["stage"] == "on_scene"
    assert app.get(f"/api/v1/incidents/{incident_id}", headers=admin).json()["status"] == "in_progress"
    assert app.post(f"/api/v1/dispatch/assignments/{assignment['id']}/progress", headers=admin,
                    json={"stage": "en_route"}).status_code == 409
    app.post(f"/api/v1/dispatch/assignments/{assignment['id']}/progress", headers=admin, json={"stage": "rescued"})
    assert app.get(f"/api/v1/resources/{first}", headers=admin).json()["status"] == "available"

    rejection = app.post(f"/api/v1/dispatch/incidents/{second_incident}/reject", headers=admin,
                         json={"reason": "Waiting for callback to confirm address"}).json()
    assert rejection["decision"] == "rejected"


def test_cancelling_returns_incident_to_verified(app, admin, submit, boat):
    incident_id = _verified(app, admin, submit, "3 people trapped by flood water")
    assignment = app.post(f"/api/v1/dispatch/incidents/{incident_id}/approve", headers=admin,
                          json={"resource_id": boat["id"]}).json()["assignment"]
    assert app.post(f"/api/v1/dispatch/assignments/{assignment['id']}/progress", headers=admin,
                    json={"stage": "cancelled"}).status_code == 409  # note required
    app.post(f"/api/v1/dispatch/assignments/{assignment['id']}/progress", headers=admin,
             json={"stage": "cancelled", "note": "Boat engine failure"})
    assert app.get(f"/api/v1/incidents/{incident_id}", headers=admin).json()["status"] == "verified"
    assert app.get(f"/api/v1/resources/{boat['id']}", headers=admin).json()["status"] == "available"


def test_queue_and_plan(app, admin, submit, boat, operation):
    _verified(app, admin, submit, "Need food for 10 people")
    urgent = _verified(app, admin, submit, "5 people trapped on roof, water rising, elderly woman")
    queue = app.get(f"/api/v1/dispatch/queue?disaster_id={operation}", headers=admin).json()
    assert queue[0]["incident_id"] == urgent
    assert queue[0]["priority_score"]["total"] > queue[1]["priority_score"]["total"]
    plan = app.get(f"/api/v1/dispatch/plan?disaster_id={operation}", headers=admin).json()
    assert plan["entries"][0]["candidate"]["callsign"] == "BOAT-1"
    assert plan["entries"][1]["candidate"] is None


def test_decision_records_what_was_recommended(app, admin, submit, boat, db):
    from sqlalchemy import text

    incident_id = _verified(app, admin, submit, "Trapped by flood, need boat")
    app.post(f"/api/v1/dispatch/incidents/{incident_id}/approve", headers=admin, json={"resource_id": boat["id"]})
    with db() as session:
        row = session.execute(text("SELECT recommendation, followed_recommendation FROM dispatch_decisions")).one()
    assert row.followed_recommendation is True
    assert row.recommendation["candidates"][0]["callsign"] == "BOAT-1"
