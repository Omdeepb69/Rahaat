"""State and district control rooms: sign-in by jurisdiction, and isolation between them."""
from __future__ import annotations

from typing import Any, Callable

import pytest

from raahat.application.identity import service as identity
from raahat.security.jurisdiction import Jurisdiction

KERALA, ERNAKULAM, THRISSUR = "32", "555", "566"
ODISHA, KHORDHA = "21", "362"


@pytest.fixture()
def issue(db) -> Callable[..., str]:
    """Create a jurisdiction account and return its generated password."""

    def _issue(state: str | None = None, district: str | None = None) -> str:
        with db() as session:
            issued = identity.provision_jurisdiction_account(
                session, jurisdiction=Jurisdiction(state, district), created_by=None
            )
            session.commit()
        assert issued.password
        return issued.password

    return _issue


@pytest.fixture()
def sign_in(app) -> Callable[..., dict[str, str]]:
    def _sign_in(password: str, state: str | None = None, district: str | None = None) -> dict[str, str]:
        level = "national" if state is None else ("district" if district else "state")
        response = app.post("/api/v1/auth/login", json={
            "level": level, "state_code": state, "district_code": district, "password": password,
        })
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _sign_in


def _open(app, headers, **codes: Any) -> dict[str, Any]:
    response = app.post("/api/v1/disasters", headers=headers, json={
        "name": "Periyar flood response", "disaster_type": "flood", **codes,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_directory_lists_every_state_and_district(app) -> None:
    body = app.get("/api/v1/jurisdictions").json()
    states = {s["code"]: s for s in body["states"]}
    assert len(states) == 36
    assert sum(len(s["districts"]) for s in body["states"]) == 790
    assert states[KERALA]["name"] == "Kerala"
    assert {"code": ERNAKULAM, "name": "Ernakulam"} in states[KERALA]["districts"]
    assert "Local Government Directory" in body["source"]


def test_sign_in_by_state_district_and_password(app, issue) -> None:
    password = issue(KERALA, ERNAKULAM)
    response = app.post("/api/v1/auth/login", json={
        "level": "district", "state_code": KERALA, "district_code": ERNAKULAM, "password": password,
    })
    assert response.status_code == 200, response.text
    profile = response.json()["user"]
    assert profile["role"] == "control_room"
    assert profile["jurisdiction"]["label"] == "Ernakulam district control room, Kerala"
    assert "users:manage" not in profile["permissions"]

    wrong = app.post("/api/v1/auth/login", json={
        "level": "district", "state_code": KERALA, "district_code": ERNAKULAM, "password": password + "x",
    })
    assert wrong.status_code == 401
    mismatched = app.post("/api/v1/auth/login", json={
        "level": "district", "state_code": ODISHA, "district_code": ERNAKULAM, "password": password,
    })
    assert mismatched.status_code == 422
    missing = app.post("/api/v1/auth/login", json={
        "level": "state", "state_code": ODISHA, "password": password,
    })
    assert missing.status_code == 401


def test_generated_passwords_are_distinct_and_strong(db) -> None:
    passwords = {identity.generate_password() for _ in range(200)}
    assert len(passwords) == 200
    assert all(len(p) == 19 and p.count("-") == 3 for p in passwords)


def test_odisha_cannot_see_kerala(app, admin, issue, sign_in) -> None:
    kerala_op = _open(app, admin, state_code=KERALA, district_code=ERNAKULAM)
    report = app.post("/api/v1/reports", headers=admin, json={
        "disaster_id": kerala_op["id"], "text": "Water entered the house, 4 people on the roof near Aluva market",
        "idempotency_key": "6f1c1f3e-5a4e-4a43-9a52-1b0c6f6b9d11",
    })
    assert report.status_code == 201, report.text
    incident_ref = report.json()["incident_reference"]
    report_id = report.json()["report"]["id"]

    odisha = sign_in(issue(ODISHA), ODISHA)
    assert app.get("/api/v1/disasters", headers=odisha).json() == []
    assert app.get(f"/api/v1/disasters/{kerala_op['id']}", headers=odisha).status_code == 404
    assert app.get(f"/api/v1/incidents/{incident_ref}", headers=odisha).status_code == 404
    assert app.get(f"/api/v1/reports/{report_id}", headers=odisha).status_code == 404
    assert app.get("/api/v1/incidents", headers=odisha, params={"disaster_id": kerala_op["id"]}).status_code == 404
    assert app.get("/api/v1/incidents", headers=odisha).status_code == 400
    assert app.post(f"/api/v1/incidents/{incident_ref}/status", headers=odisha,
                    json={"status": "verified"}).status_code == 404
    events = app.get("/api/v1/events", headers=odisha, params={"after": 0}).json()["items"]
    assert all(e["disaster_id"] != kerala_op["id"] for e in events)
    audit = app.get("/api/v1/audit/events", headers=odisha).json()["items"]
    assert audit == []

    kerala = sign_in(issue(KERALA), KERALA)
    assert [d["id"] for d in app.get("/api/v1/disasters", headers=kerala).json()] == [kerala_op["id"]]
    assert app.get(f"/api/v1/incidents/{incident_ref}", headers=kerala).status_code == 200

    ernakulam = sign_in(issue(KERALA, ERNAKULAM), KERALA, ERNAKULAM)
    assert app.get(f"/api/v1/incidents/{incident_ref}", headers=ernakulam).status_code == 200
    thrissur = sign_in(issue(KERALA, THRISSUR), KERALA, THRISSUR)
    assert app.get(f"/api/v1/incidents/{incident_ref}", headers=thrissur).status_code == 404
    assert app.get("/api/v1/disasters", headers=thrissur).json() == []


def test_operations_open_inside_the_creators_jurisdiction(app, issue, sign_in) -> None:
    ernakulam = sign_in(issue(KERALA, ERNAKULAM), KERALA, ERNAKULAM)
    own = _open(app, ernakulam)
    assert (own["state_code"], own["district_code"]) == (KERALA, ERNAKULAM)
    assert own["jurisdiction"] == "Ernakulam district control room, Kerala"
    elsewhere = app.post("/api/v1/disasters", headers=ernakulam, json={
        "name": "Not ours", "disaster_type": "flood", "state_code": KERALA, "district_code": THRISSUR,
    })
    assert elsewhere.status_code == 403

    kerala = sign_in(issue(KERALA), KERALA)
    district_op = _open(app, kerala, district_code=THRISSUR)
    assert district_op["district_code"] == THRISSUR
    state_op = _open(app, kerala)
    assert (state_op["state_code"], state_op["district_code"]) == (KERALA, None)
    assert app.post("/api/v1/disasters", headers=kerala, json={
        "name": "Not ours", "disaster_type": "flood", "state_code": ODISHA,
    }).status_code == 403


def test_only_national_issues_passwords(app, admin, issue, sign_in) -> None:
    issued = app.post("/api/v1/users/jurisdictions/issue", headers=admin, json={
        "level": "district", "state_code": ODISHA, "district_code": KHORDHA,
    })
    assert issued.status_code == 200, issued.text
    body = issued.json()
    assert body["created"] is True
    assert body["user"]["jurisdiction"] == "Khordha district control room, Odisha"
    sign_in(body["password"], ODISHA, KHORDHA)

    again = app.post("/api/v1/users/jurisdictions/issue", headers=admin, json={
        "level": "district", "state_code": ODISHA, "district_code": KHORDHA,
    }).json()
    assert again["created"] is False and again["password"] != body["password"]
    stale = app.post("/api/v1/auth/login", json={
        "level": "district", "state_code": ODISHA, "district_code": KHORDHA, "password": body["password"],
    })
    assert stale.status_code == 401

    kerala = sign_in(issue(KERALA), KERALA)
    assert app.post("/api/v1/users/jurisdictions/issue", headers=kerala, json={
        "level": "state", "state_code": KERALA,
    }).status_code == 403
