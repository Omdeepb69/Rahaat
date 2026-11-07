"""Integration tests for Resource registry, availability tracking, PostGIS spatial queries, and REST endpoints."""
from __future__ import annotations

import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models import DisasterModel, OutboxEventModel, ReportModel
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.models.resource import ResourceModel
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
def db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    with session_factory() as session:
        session.query(EntityMergeEventModel).delete()
        session.query(AuditEventModel).delete()
        session.query(ResourceModel).delete()
        session.query(IncidentLinkModel).delete()
        session.query(IncidentReportModel).delete()
        session.query(LocationHypothesisModel).delete()
        session.query(IncidentModel).delete()
        session.query(OutboxEventModel).delete()
        session.query(ReportModel).delete()
        session.query(DisasterModel).delete()
        session.commit()
        yield session


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestResourcesIntegrationAPI:
    def test_register_resource_unauthorized_without_dispatcher_header(
        self, client: TestClient, db_session: Session
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Cyclone 2026", disaster_type="cyclone")
        db_session.add(disaster)
        db_session.commit()

        payload = {
            "disaster_id": str(disaster.id),
            "resource_type": "boat",
            "name": "Rescue Boat 1",
            "capacity": 6,
        }
        res = client.post("/api/v1/resources", json=payload)
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_register_and_get_resource_success(
        self, client: TestClient, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Cyclone 2026", disaster_type="cyclone")
        db_session.add(disaster)
        db_session.commit()

        dispatcher_id = uuid.uuid4()
        payload = {
            "disaster_id": str(disaster.id),
            "resource_type": "boat",
            "name": "Panaji Rescue Boat A",
            "capacity": 10,
            "availability_status": "available",
            "latitude": 15.4989,
            "longitude": 73.8278,
        }

        # 1. Register resource via POST
        res = client.post(
            "/api/v1/resources",
            json=payload,
            headers={"X-Dispatcher-Id": str(dispatcher_id)},
        )
        assert res.status_code == 201
        data = res.json()
        resource_id = uuid.UUID(data["id"])

        assert data["name"] == "Panaji Rescue Boat A"
        assert data["resource_type"] == "boat"
        assert data["capacity"] == 10
        assert data["availability_status"] == "available"
        assert data["location"]["latitude"] == pytest.approx(15.4989, abs=0.0001)
        assert data["location"]["longitude"] == pytest.approx(73.8278, abs=0.0001)

        # 2. Get resource via GET /resources/{id}
        get_res = client.get(f"/api/v1/resources/{resource_id}")
        assert get_res.status_code == 200
        get_data = get_res.json()
        assert get_data["id"] == str(resource_id)
        assert get_data["name"] == "Panaji Rescue Boat A"

        # 3. Verify PostgreSQL database row and audit record
        with session_factory() as session:
            model = session.get(ResourceModel, resource_id)
            assert model is not None
            assert model.name == "Panaji Rescue Boat A"
            assert model.availability_status == "available"
            assert model.location is not None

            audit = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_type == "resource",
                    AuditEventModel.entity_id == resource_id,
                    AuditEventModel.action == "resource.registered",
                )
            ).first()
            assert audit is not None
            assert audit.actor_id == dispatcher_id
            assert audit.hash is not None

    def test_list_and_spatial_proximity_search(
        self, client: TestClient, db_session: Session
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Flood 2026", disaster_type="flood")
        db_session.add(disaster)
        db_session.commit()

        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        # Panaji Boat (Panaji coordinates: 15.4989, 73.8278)
        client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "boat",
                "name": "Panaji Boat",
                "latitude": 15.4989,
                "longitude": 73.8278,
            },
            headers=headers,
        )

        # Margao Boat (~28 km south: 15.2736, 73.9582)
        client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "boat",
                "name": "Margao Boat",
                "latitude": 15.2736,
                "longitude": 73.9582,
            },
            headers=headers,
        )

        # Medical Team in Panaji
        client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "medical_team",
                "name": "Panaji Medical Team",
                "latitude": 15.5000,
                "longitude": 73.8300,
            },
            headers=headers,
        )

        # 1. Plain list query by disaster
        all_res = client.get(f"/api/v1/resources?disaster_id={disaster.id}")
        assert all_res.status_code == 200
        assert len(all_res.json()) == 3

        # 2. Type filtering
        boats_res = client.get(f"/api/v1/resources?disaster_id={disaster.id}&resource_type=boat")
        assert boats_res.status_code == 200
        assert len(boats_res.json()) == 2

        # 3. Spatial proximity query: 5km around Panaji center (15.4989, 73.8278)
        # Should return Panaji Boat and Panaji Medical Team, but NOT Margao Boat
        spatial_res = client.get(
            f"/api/v1/resources?disaster_id={disaster.id}&lat=15.4989&lon=73.8278&radius_meters=5000"
        )
        assert spatial_res.status_code == 200
        spatial_items = spatial_res.json()
        assert len(spatial_items) == 2
        names = [item["name"] for item in spatial_items]
        assert "Panaji Boat" in names
        assert "Panaji Medical Team" in names
        assert "Margao Boat" not in names
        assert all(item["distance_meters"] is not None for item in spatial_items)
        assert all(item["distance_meters"] <= 5000.0 for item in spatial_items)

        # 4. Spatial query with type filter (only boats within 5km of Panaji)
        boat_spatial_res = client.get(
            f"/api/v1/resources?disaster_id={disaster.id}&resource_type=boat&lat=15.4989&lon=73.8278&radius_meters=5000"
        )
        assert boat_spatial_res.status_code == 200
        boat_items = boat_spatial_res.json()
        assert len(boat_items) == 1
        assert boat_items[0]["name"] == "Panaji Boat"

    def test_update_resource_status_api(
        self, client: TestClient, db_session: Session, session_factory: sessionmaker[Session]
    ) -> None:
        disaster = DisasterModel(id=uuid.uuid4(), name="Flood 2026", disaster_type="flood")
        db_session.add(disaster)
        db_session.commit()

        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        reg_res = client.post(
            "/api/v1/resources",
            json={
                "disaster_id": str(disaster.id),
                "resource_type": "vehicle",
                "name": "High Clearance Truck 1",
                "latitude": 15.40,
                "longitude": 73.95,
            },
            headers=headers,
        )
        resource_id = reg_res.json()["id"]

        # Patch status to assigned with new location coordinates
        patch_res = client.patch(
            f"/api/v1/resources/{resource_id}/status",
            json={
                "availability_status": "assigned",
                "latitude": 15.42,
                "longitude": 73.97,
                "reason": "Dispatched to Sector 4 flood rescue",
            },
            headers=headers,
        )
        assert patch_res.status_code == 200
        patch_data = patch_res.json()
        assert patch_data["availability_status"] == "assigned"
        assert patch_data["location"]["latitude"] == pytest.approx(15.42, abs=0.0001)

        # Verify audit record in database
        with session_factory() as session:
            audit = session.scalars(
                select(AuditEventModel).where(
                    AuditEventModel.entity_type == "resource",
                    AuditEventModel.entity_id == uuid.UUID(resource_id),
                    AuditEventModel.action == "resource.status_updated",
                )
            ).first()
            assert audit is not None
            assert audit.payload["previous_status"] == "available"
            assert audit.payload["new_status"] == "assigned"
            assert audit.payload["reason"] == "Dispatched to Sector 4 flood rescue"

    def test_get_resource_404_not_found(self, client: TestClient) -> None:
        res = client.get(f"/api/v1/resources/{uuid.uuid4()}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
