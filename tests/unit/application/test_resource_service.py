"""Unit tests for ResourceService: registration, lifecycle status updates, spatial proximity queries, and audit logging."""
from __future__ import annotations

import uuid

import pytest

from raahat.application.resources.service import ResourceService
from raahat.domain.resources.repository import InMemoryResourceRepository
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import ResourceStatus, ResourceType
from raahat.infrastructure.database.repositories.audit import InMemoryAuditRepository


class TestResourceService:
    @pytest.fixture
    def resource_repo(self) -> InMemoryResourceRepository:
        return InMemoryResourceRepository()

    @pytest.fixture
    def audit_repo(self) -> InMemoryAuditRepository:
        return InMemoryAuditRepository()

    @pytest.fixture
    def service(
        self,
        resource_repo: InMemoryResourceRepository,
        audit_repo: InMemoryAuditRepository,
    ) -> ResourceService:
        return ResourceService(
            resource_repo=resource_repo,
            audit_repo=audit_repo,
        )

    def test_register_resource_success(
        self,
        service: ResourceService,
        audit_repo: InMemoryAuditRepository,
    ) -> None:
        disaster_id = uuid.uuid4()
        dispatcher_id = uuid.uuid4()
        coords = PointCoordinates(latitude=15.40, longitude=73.95)

        resource = service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="NDRF Inflatable Boat 4",
            capacity=8,
            availability_status=ResourceStatus.AVAILABLE,
            location=coords,
            registered_by=dispatcher_id,
        )

        assert resource.id is not None
        assert resource.disaster_id == disaster_id
        assert resource.resource_type == ResourceType.BOAT
        assert resource.name == "NDRF Inflatable Boat 4"
        assert resource.capacity == 8
        assert resource.availability_status == ResourceStatus.AVAILABLE
        assert resource.location == coords

        # Audit event verification
        assert len(audit_repo.events) == 1
        event = audit_repo.events[0]
        assert event.action == "resource.registered"
        assert event.actor_id == dispatcher_id
        assert event.entity_type == "resource"
        assert event.entity_id == resource.id
        assert event.payload["resource_type"] == "boat"
        assert event.payload["capacity"] == 8

    def test_list_resources_with_filtering(
        self, service: ResourceService
    ) -> None:
        disaster_id = uuid.uuid4()
        other_disaster = uuid.uuid4()

        service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="Boat 1",
            availability_status=ResourceStatus.AVAILABLE,
        )
        service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="Boat 2",
            availability_status=ResourceStatus.ASSIGNED,
        )
        service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.MEDICAL_TEAM,
            name="Medical Unit 1",
            availability_status=ResourceStatus.AVAILABLE,
        )
        service.register_resource(
            disaster_id=other_disaster,
            resource_type=ResourceType.BOAT,
            name="Other Disaster Boat",
            availability_status=ResourceStatus.AVAILABLE,
        )

        # Filter by disaster only
        all_disaster = service.list_resources(disaster_id=disaster_id)
        assert len(all_disaster) == 3

        # Filter by type
        boats = service.list_resources(disaster_id=disaster_id, resource_type=ResourceType.BOAT)
        assert len(boats) == 2
        assert all(b.resource_type == ResourceType.BOAT for b in boats)

        # Filter by status
        available_boats = service.list_resources(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            status=ResourceStatus.AVAILABLE,
        )
        assert len(available_boats) == 1
        assert available_boats[0].name == "Boat 1"

    def test_find_nearby_resources_ordered_by_distance(
        self, service: ResourceService
    ) -> None:
        disaster_id = uuid.uuid4()
        center = PointCoordinates(latitude=15.4000, longitude=73.9500)

        # Asset A: ~111 meters north
        res_a = service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="Close Boat A",
            location=PointCoordinates(latitude=15.4010, longitude=73.9500),
        )

        # Asset B: ~2.2 km north
        res_b = service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="Mid Boat B",
            location=PointCoordinates(latitude=15.4200, longitude=73.9500),
        )

        # Asset C: ~66 km north (out of range)
        service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.BOAT,
            name="Far Boat C",
            location=PointCoordinates(latitude=16.0000, longitude=73.9500),
        )

        nearby = service.find_nearby_resources(
            disaster_id=disaster_id,
            coordinates=center,
            radius_meters=5000.0,  # 5 km search radius
        )

        assert len(nearby) == 2
        assert nearby[0].resource.id == res_a.id
        assert nearby[0].distance_meters < nearby[1].distance_meters
        assert nearby[1].resource.id == res_b.id

    def test_update_resource_status_and_location(
        self,
        service: ResourceService,
        audit_repo: InMemoryAuditRepository,
    ) -> None:
        disaster_id = uuid.uuid4()
        dispatcher_id = uuid.uuid4()

        res = service.register_resource(
            disaster_id=disaster_id,
            resource_type=ResourceType.VEHICLE,
            name="Rescue Truck 1",
            availability_status=ResourceStatus.AVAILABLE,
            location=PointCoordinates(latitude=15.40, longitude=73.95),
        )

        new_coords = PointCoordinates(latitude=15.45, longitude=73.98)
        updated = service.update_resource_status(
            resource_id=res.id,
            status=ResourceStatus.MAINTENANCE,
            location=new_coords,
            updated_by=dispatcher_id,
            reason="Scheduled tire replacement",
        )

        assert updated.availability_status == ResourceStatus.MAINTENANCE
        assert updated.location == new_coords

        # Verify audit event
        assert len(audit_repo.events) == 2
        status_event = audit_repo.events[1]
        assert status_event.action == "resource.status_updated"
        assert status_event.actor_id == dispatcher_id
        assert status_event.payload["previous_status"] == "available"
        assert status_event.payload["new_status"] == "maintenance"
        assert status_event.payload["reason"] == "Scheduled tire replacement"

    def test_update_nonexistent_resource_raises_error(
        self, service: ResourceService
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            service.update_resource_status(
                resource_id=uuid.uuid4(),
                status=ResourceStatus.OFFLINE,
            )

