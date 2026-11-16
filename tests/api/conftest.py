"""Fixtures for API tests: a clean database per test and authenticated clients."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from raahat.api import deps, services
from raahat.application.identity import service as identity
from raahat.config import get_settings
from raahat.security.permissions import Role

PASSWORD = "Correct-Horse-Battery-77"
APP_TABLES = (
    "dispatch_decisions, operation_events, assignments, entity_merge_events, incident_links, "
    "location_hypotheses, evidence_spans, evidence_items, incident_reports, processing_runs, "
    "incidents, reports, resources, landmarks, integration_checks, worker_heartbeats, "
    "external_observations, audit_events, users, disasters"
)


def _reset_process_state() -> None:
    get_settings.cache_clear()
    deps.reset_engine()
    deps.rate_limiter.reset()
    services.reset_services()


@pytest.fixture()
def db() -> Iterator[Any]:
    _reset_process_state()
    factory = deps.get_session_factory()
    with factory() as session:
        session.execute(text(f"TRUNCATE {APP_TABLES} RESTART IDENTITY CASCADE"))
        session.execute(text("ALTER SEQUENCE incident_reference_seq RESTART WITH 1"))
        session.commit()
    yield factory
    _reset_process_state()


@pytest.fixture()
def app(db) -> Iterator[Any]:
    from raahat.api.app import create_app

    application = create_app(get_settings())
    with TestClient(application) as client:
        yield client


@pytest.fixture()
def make_user(db) -> Callable[..., dict[str, Any]]:
    def _make(username: str, role: Role, *, must_change: bool = False) -> dict[str, Any]:
        with db() as session:
            user = identity.create_user(
                session, username=username, full_name=username.title(), role=role,
                password=PASSWORD, created_by=None, must_change_password=must_change,
            )
            session.commit()
            return {"id": user.id, "username": username, "role": role}

    return _make


@pytest.fixture()
def login(app) -> Callable[[str], dict[str, str]]:
    def _login(username: str, password: str = PASSWORD) -> dict[str, str]:
        response = app.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


@pytest.fixture()
def admin(make_user, login) -> dict[str, str]:
    make_user("chief", Role.ADMIN)
    return login("chief")


@pytest.fixture()
def operation(app, admin) -> str:
    response = app.post(
        "/api/v1/disasters",
        headers=admin,
        json={
            "name": "Test operation (fixture)",
            "disaster_type": "flood",
            "map_center": {"latitude": 10.0, "longitude": 76.3},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture()
def submit(app, admin, operation) -> Callable[..., dict[str, Any]]:
    def _submit(text_value: str, headers: dict[str, str] | None = None, **extra: Any) -> dict[str, Any]:
        body = {
            "disaster_id": operation,
            "text": text_value,
            "idempotency_key": str(uuid.uuid4()),
            **extra,
        }
        response = app.post("/api/v1/reports", headers=headers or admin, json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _submit
