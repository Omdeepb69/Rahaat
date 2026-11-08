"""Integration tests for disasters API endpoints."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

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


def test_list_and_active_disasters(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    # 1. Seed a disaster record
    disaster_id = uuid.uuid4()
    with session_factory() as session:
        d = DisasterModel(
            id=disaster_id,
            name="Kerala Floods 2018 — Test Context",
            disaster_type="flood",
            status="active",
        )
        session.add(d)
        session.commit()

    # 2. Test list disasters
    res = client.get("/api/v1/disasters")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert any(item["name"] == "Kerala Floods 2018 — Test Context" for item in data)

    # 3. Test active disaster
    res_active = client.get("/api/v1/disasters/active")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert "id" in active_data
    assert "name" in active_data

    # 4. Test disaster detail
    res_detail = client.get(f"/api/v1/disasters/{disaster_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["id"] == str(disaster_id)
