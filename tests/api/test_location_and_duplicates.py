"""Location evidence, landmark candidates and duplicate review."""
from __future__ import annotations

import uuid

from raahat.infrastructure.database.models.location import LandmarkModel


def _landmark(db, name: str, lat: float, lon: float, kind: str = "education") -> None:
    with db() as session:
        session.add(LandmarkModel(
            id=uuid.uuid4(), name=name, kind=kind, source="operator", salience=1.0,
            location=f"SRID=4326;POINT({lon} {lat})", metadata_={"fixture": True},
        ))
        session.commit()


def test_landmark_mentions_become_candidates_not_positions(app, admin, submit, db):
    _landmark(db, "St Marys School", 10.01, 76.31)
    created = submit("Water entered our house behind St Marys School, 4 people")
    incident = app.get(f"/api/v1/incidents/{created['incident_id']}", headers=admin).json()
    assert incident["location"]["status"] == "candidate"
    candidate = incident["location_candidates"][0]
    assert candidate["source"] == "landmark"
    assert candidate["verification_status"] == "candidate"
    assert candidate["source_detail"]["matched_phrase"]
    assert candidate["source_detail"]["radius_basis"] == "assumed"


def test_confirming_and_rejecting_candidates(app, admin, submit, db):
    _landmark(db, "Old Bridge Junction", 10.02, 76.32, kind="bridge")
    _landmark(db, "Old Bridge Road", 10.20, 76.40, kind="locality")
    created = submit("Stuck near the Old Bridge, water rising")
    incident = app.get(f"/api/v1/incidents/{created['incident_id']}", headers=admin).json()
    assert len(incident["location_candidates"]) >= 2
    first, second = incident["location_candidates"][:2]
    confirmed = app.post(
        f"/api/v1/incidents/{incident['id']}/location-candidates/{second['id']}/confirm",
        headers=admin, json={"note": "Caller described the junction"},
    ).json()
    assert confirmed["location"]["status"] == "confirmed"
    assert confirmed["location"]["coordinates"] == second["coordinates"]
    rejected = app.post(
        f"/api/v1/incidents/{incident['id']}/location-candidates/{second['id']}/reject",
        headers=admin, json={},
    ).json()
    assert rejected["location"]["status"] == "candidate"


def test_operator_position_is_recorded_with_provenance(app, admin, submit):
    incident_id = submit("Family stranded")["incident_id"]
    result = app.put(
        f"/api/v1/incidents/{incident_id}/location", headers=admin,
        json={"latitude": 10.05, "longitude": 76.33, "label": "Placed on map"},
    ).json()
    assert result["location"]["status"] == "confirmed"
    assert result["location"]["source"] == "operator"
    bad = app.put(f"/api/v1/incidents/{incident_id}/location", headers=admin,
                  json={"latitude": 0, "longitude": 0})
    assert bad.status_code == 422


def test_geocoder_lookup_reports_not_configured(app, admin, submit):
    incident_id = submit("Near Kakkanad")["incident_id"]
    response = app.post(f"/api/v1/incidents/{incident_id}/location-candidates/geocode",
                        headers=admin, json={"query": "Kakkanad"})
    assert response.status_code == 503


def test_duplicates_are_held_for_review_with_signals(app, admin, submit):
    first = submit("6 people trapped, water rising", caller_contact="+919800000001",
                   latitude=10.05, longitude=76.32)
    second = submit("ഞങ്ങൾ ആറ് പേർ കുടുങ്ങി", caller_contact="+919800000001",
                    latitude=10.0501, longitude=76.3201)
    assert second["is_new_incident"] is True  # never merged automatically
    assert second["duplicate_candidates"] == 1
    detail = app.get(f"/api/v1/incidents/{second['incident_id']}", headers=admin).json()
    candidate = detail["duplicates"][0]
    assert candidate["other"]["id"] == first["incident_id"]
    assert candidate["status"] == "pending_review"
    assert any(s["name"] == "phone_match" for s in candidate["signals"])
    pending = app.get("/api/v1/incidents/duplicates/pending", headers=admin).json()
    assert pending["total"] == 1


def test_merge_preserves_reports_and_can_be_reversed(app, admin, submit):
    first = submit("6 people trapped", caller_contact="+919800000002", latitude=10.05, longitude=76.32)
    second = submit("Six people trapped here", caller_contact="+919800000002", latitude=10.0501, longitude=76.3201)
    link = app.get(f"/api/v1/incidents/{second['incident_id']}", headers=admin).json()["duplicates"][0]
    merged = app.post(
        f"/api/v1/incidents/{second['incident_id']}/duplicates/{link['link_id']}/review",
        headers=admin, json={"action": "merge", "reason": "Same phone, same household"},
    ).json()
    assert merged["status"] == "duplicate"
    assert merged["merged_into_id"] == first["incident_id"]
    survivor = app.get(f"/api/v1/incidents/{first['incident_id']}", headers=admin).json()
    assert survivor["report_count"] == 2
    restored = app.post(
        f"/api/v1/incidents/{second['incident_id']}/unmerge", headers=admin,
        json={"reason": "Callback: different houses"},
    ).json()
    assert restored["status"] == "unverified"
    survivor = app.get(f"/api/v1/incidents/{first['incident_id']}", headers=admin).json()
    assert survivor["report_count"] == 1


def test_rejecting_a_duplicate_keeps_both(app, admin, submit):
    submit("Trapped", caller_contact="+919800000003", latitude=10.05, longitude=76.32)
    second = submit("Trapped too", caller_contact="+919800000003", latitude=10.05, longitude=76.32)
    link = app.get(f"/api/v1/incidents/{second['incident_id']}", headers=admin).json()["duplicates"][0]
    result = app.post(
        f"/api/v1/incidents/{second['incident_id']}/duplicates/{link['link_id']}/review",
        headers=admin, json={"action": "reject", "reason": "Different families"},
    ).json()
    assert result["status"] == "unverified"
    assert result["duplicates"][0]["status"] == "rejected"
    assert result["duplicates"][0]["review_reason"] == "Different families"


def test_old_incidents_are_matched_only_by_phone_or_position(app, admin, submit, db):
    from sqlalchemy import text

    old = submit("Trapped on the roof, water rising", caller_contact="+919800000077", latitude=10.05, longitude=76.32)
    with db() as session:
        session.execute(text("UPDATE incidents SET created_at = now() - interval '2 days'"))
        session.commit()
    unrelated = submit("Need drinking water", caller_contact="+919811111111", latitude=10.40, longitude=76.60)
    assert unrelated["duplicate_candidates"] == 0
    same_phone = submit("Still trapped", caller_contact="+91 98000 00077")
    assert same_phone["duplicate_candidates"] >= 1
    nearby = submit("Trapped on the roof, water rising", latitude=10.0501, longitude=76.3201)
    detail = app.get(f"/api/v1/incidents/{nearby['incident_id']}", headers=admin).json()
    assert any(d["other"]["id"] == old["incident_id"] for d in detail["duplicates"])
