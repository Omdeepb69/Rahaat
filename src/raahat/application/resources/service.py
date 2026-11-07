"""Resource management service for registering, querying, and updating rescue assets."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.operations.operation import Resource
from raahat.domain.resources.repository import InMemoryResourceRepository, ResourceRepository
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import ResourceStatus, ResourceType
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    InMemoryAuditRepository,
)

logger = logging.getLogger(__name__)


class ResourceNearby(BaseModel):
    """Resource paired with calculated distance in meters from query location."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resource: Resource
    distance_meters: float


class ResourceService:
    """Manages the lifecycle, spatial querying, and availability status of rescue resources."""

    def __init__(
        self,
        resource_repo: Optional[ResourceRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._resource_repo = resource_repo or InMemoryResourceRepository()
        self._audit_repo = audit_repo or InMemoryAuditRepository()
        self._session_factory = session_factory

    def register_resource(
        self,
        disaster_id: uuid.UUID,
        resource_type: ResourceType,
        name: str,
        capacity: Optional[int] = None,
        availability_status: ResourceStatus = ResourceStatus.AVAILABLE,
        location: Optional[PointCoordinates] = None,
        registered_by: Optional[uuid.UUID] = None,
        session: Optional[Session] = None,
    ) -> Resource:
        """Register a new disaster rescue asset and record audit event."""
        resource = Resource(
            disaster_id=disaster_id,
            resource_type=resource_type,
            name=name,
            capacity=capacity,
            availability_status=availability_status,
            location=location,
        )

        saved = self._resource_repo.save(resource, session=session)

        self._audit_repo.record_event(
            action="resource.registered",
            actor_id=registered_by,
            entity_type="resource",
            entity_id=saved.id,
            payload={
                "disaster_id": str(disaster_id),
                "resource_type": resource_type.value,
                "name": name,
                "capacity": capacity,
                "availability_status": availability_status.value,
                "has_location": location is not None,
                "latitude": location.latitude if location else None,
                "longitude": location.longitude if location else None,
            },
        )
        return saved

    def get_resource(
        self,
        resource_id: uuid.UUID,
        session: Optional[Session] = None,
    ) -> Optional[Resource]:
        """Retrieve a rescue resource by ID."""
        return self._resource_repo.get_by_id(resource_id, session=session)

    def list_resources(
        self,
        disaster_id: uuid.UUID,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        session: Optional[Session] = None,
    ) -> list[Resource]:
        """List resources for a disaster with optional type and status filtering."""
        return self._resource_repo.list_by_disaster(
            disaster_id=disaster_id,
            resource_type=resource_type,
            status=status,
            session=session,
        )

    def find_nearby_resources(
        self,
        disaster_id: uuid.UUID,
        coordinates: PointCoordinates,
        radius_meters: float,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        limit: int = 50,
        session: Optional[Session] = None,
    ) -> list[ResourceNearby]:
        """Find resources within radius_meters, ordered by distance ascending."""
        scored = self._resource_repo.find_nearby(
            disaster_id=disaster_id,
            coordinates=coordinates,
            radius_meters=radius_meters,
            resource_type=resource_type,
            status=status,
            limit=limit,
            session=session,
        )
        return [
            ResourceNearby(resource=res, distance_meters=dist)
            for res, dist in scored
        ]

    def update_resource_status(
        self,
        resource_id: uuid.UUID,
        status: ResourceStatus,
        location: Optional[PointCoordinates] = None,
        updated_by: Optional[uuid.UUID] = None,
        reason: Optional[str] = None,
        session: Optional[Session] = None,
    ) -> Resource:
        """Update resource availability status and optional location with audit logging."""
        existing = self._resource_repo.get_by_id(resource_id, session=session)
        if existing is None:
            raise ValueError(f"Resource {resource_id} not found")

        old_status = existing.availability_status
        updated = self._resource_repo.update_status(
            resource_id=resource_id,
            status=status,
            location=location,
            session=session,
        )
        if updated is None:
            raise ValueError(f"Resource {resource_id} not found")

        self._audit_repo.record_event(
            action="resource.status_updated",
            actor_id=updated_by,
            entity_type="resource",
            entity_id=resource_id,
            payload={
                "previous_status": old_status.value,
                "new_status": status.value,
                "reason": reason,
                "has_location_update": location is not None,
                "latitude": location.latitude if location else None,
                "longitude": location.longitude if location else None,
            },
        )
        return updated

