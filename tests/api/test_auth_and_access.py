"""Authentication, session handling and role-based access."""
from __future__ import annotations

from raahat.security.permissions import Role
from tests.api.conftest import PASSWORD


def test_every_data_endpoint_requires_authentication(app):
    for path in ("/api/v1/incidents", "/api/v1/reports", "/api/v1/resources", "/api/v1/disasters",
                 "/api/v1/system/status", "/api/v1/audit/events", "/api/v1/users", "/api/v1/events/stream"):
        assert app.get(path).status_code == 401, path


def test_health_endpoints_are_public_and_check_the_database(app):
    assert app.get("/health/live").json() == {"status": "ok"}
    ready = app.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"


def test_login_rejects_wrong_password_and_unknown_user_identically(app, make_user):
    make_user("alice", Role.OPERATOR)
    wrong = app.post("/api/v1/auth/login", json={"username": "alice", "password": "not-the-password"})
    unknown = app.post("/api/v1/auth/login", json={"username": "nobody", "password": "not-the-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_repeated_failures_lock_the_account(app, make_user):
    make_user("bob", Role.OPERATOR)
    for _ in range(5):
        app.post("/api/v1/auth/login", json={"username": "bob", "password": "wrong-password-1"})
    locked = app.post("/api/v1/auth/login", json={"username": "bob", "password": PASSWORD})
    assert locked.status_code == 423


def test_tampered_token_is_rejected(app, make_user, login):
    make_user("carol", Role.OBSERVER)
    headers = login("carol")
    token = headers["Authorization"][7:]
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert app.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_deactivation_ends_existing_sessions(app, admin, make_user, login):
    user = make_user("dave", Role.OPERATOR)
    headers = login("dave")
    assert app.get("/api/v1/auth/me", headers=headers).status_code == 200
    response = app.patch(f"/api/v1/users/{user['id']}", headers=admin, json={"is_active": False})
    assert response.status_code == 200
    assert app.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_new_user_must_change_initial_password(app, admin, login):
    created = app.post(
        "/api/v1/users", headers=admin,
        json={"username": "erin", "full_name": "Erin", "role": "observer", "initial_password": PASSWORD},
    )
    assert created.status_code == 201
    headers = login("erin")
    assert app.get("/api/v1/incidents", headers=headers).status_code == 403
    changed = app.post(
        "/api/v1/auth/change-password", headers=headers,
        json={"current_password": PASSWORD, "new_password": "A-Different-Long-Pass-5"},
    )
    assert changed.status_code == 200
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert app.get("/api/v1/incidents", headers=fresh).status_code == 200
    # The token issued before the change no longer works.
    assert app.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_weak_password_rejected(app, admin):
    response = app.post(
        "/api/v1/users", headers=admin,
        json={"username": "frank", "full_name": "Frank", "role": "observer", "initial_password": "short"},
    )
    assert response.status_code == 422


def test_last_admin_cannot_be_removed(app, admin, db):
    from sqlalchemy import select

    from raahat.infrastructure.database.models.user import UserModel

    with db() as session:
        chief = session.execute(select(UserModel).where(UserModel.username == "chief")).scalar_one()
    assert app.patch(f"/api/v1/users/{chief.id}", headers=admin, json={"role": "observer"}).status_code == 409


def test_observer_can_read_but_not_write(app, operation, make_user, login, submit):
    submit("Water rising near the market, 3 people trapped", caller_name="Test Caller", caller_contact="+910000000000")
    make_user("olga", Role.OBSERVER)
    headers = login("olga")
    reports = app.get("/api/v1/reports", headers=headers).json()
    assert reports["total"] == 1
    item = reports["items"][0]
    assert item["caller_contact"] is None and item["caller_name"] is None
    assert item["caller_details_redacted"] is True
    attempt = app.post(
        "/api/v1/reports", headers=headers,
        json={"disaster_id": operation, "text": "x", "idempotency_key": "00000000-0000-0000-0000-000000000001"},
    )
    assert attempt.status_code == 403


def test_resource_coordinator_cannot_dispatch(app, operation, make_user, login, submit):
    created = submit("Two people trapped on roof, water rising")
    make_user("rita", Role.RESOURCE_COORDINATOR)
    headers = login("rita")
    response = app.post(
        f"/api/v1/dispatch/incidents/{created['incident_id']}/approve", headers=headers,
        json={"resource_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 403


def test_cors_allows_only_configured_origin(app):
    allowed = app.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://frontend.test", "Access-Control-Request-Method": "POST"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://frontend.test"
    denied = app.options(
        "/api/v1/auth/login",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_oversized_body_rejected(app, admin):
    response = app.post(
        "/api/v1/auth/login", content=b"x" * (2 * 1024 * 1024),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
