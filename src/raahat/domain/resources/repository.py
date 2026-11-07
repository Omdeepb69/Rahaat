"""Resource repository protocol and in-memory test double."""
from __future__ import annotations

import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from raahat.domain.operations.operation import Resource
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import ResourceStatus, ResourceType


@runtime_checkable
class ResourceRepository(Protocol):
    """Protocol for persisting and querying disaster rescue assets and assets availability."""

    def save(
        self,
        resource: Resource,
        session: Optional[Any] = None,
    ) -> Resource:
        """Persist or update a rescue resource."""
        ...

    def get_by_id(
        self,
        resource_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[Resource]:
        """Retrieve a resource by its unique identifier."""
        ...

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        session: Optional[Any] = None,
    ) -> list[Resource]:
        """List resources for a disaster with optional type and status filtering."""
        ...

    def find_nearby(
        self,
        disaster_id: uuid.UUID,
        coordinates: PointCoordinates,
        radius_meters: float,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        limit: int = 50,
        session: Optional[Any] = None,
    ) -> list[tuple[Resource, float]]:
        """Find resources within radius_meters, ordered by spatial distance ascending."""
        ...

    def update_status(
        self,
        resource_id: uuid.UUID,
        status: ResourceStatus,
        location: Optional[PointCoordinates] = None,
        session: Optional[Any] = None,
    ) -> Optional[Resource]:
        """Update a resource's availability status and optionally location coordinates."""
        ...


class InMemoryResourceRepository:
    """Pure-Python in-memory implementation of ResourceRepository for fast unit testing."""

    def __init__(self) -> None:
        self._resources: dict[uuid.UUID, Resource] = {}

    def save(
        self,
        resource: Resource,
        session: Optional[Any] = None,
    ) -> Resource:
        self._resources[resource.id] = resource
        return resource

    def get_by_id(
        self,
        resource_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[Resource]:
        return self._resources.get(resource_id)

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        session: Optional[Any] = None,
    ) -> list[Resource]:
        matches: list[Resource] = []
        for res in self._resources.values():
            if res.disaster_id != disaster_id:
                continue
            if resource_type is not None and res.resource_type != resource_type:
                continue
            if status is not None and res.availability_status != status:
                continue
            matches.append(res)
        return matches

    def find_nearby(
        self,
        disaster_id: uuid.UUID,
        coordinates: PointCoordinates,
        radius_meters: float,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        limit: int = 50,
        session: Optional[Any] = None,
    ) -> list[tuple[Resource, float]]:
        candidates = self.list_by_disaster(
            disaster_id=disaster_id,
            resource_type=resource_type,
            status=status,
            session=session,
        )
        scored: list[tuple[Resource, float]] = []
        for res in candidates:
            if res.location is None:
                continue
            dist = coordinates.distance_to(res.location)
            if dist <= radius_meters:
                scored.append((res, dist))

        scored.sort(key=lambda pair: pair[1])
        return scored[:limit]

    def update_status(
        self,
        resource_id: uuid.UUID,
        status: ResourceStatus,
        location: Optional[PointCoordinates] = None,
        session: Optional[Any] = None,
    ) -> Optional[Resource]:
        res = self._resources.get(resource_id)
        if res is None:
            return None
        updated = res.model_copy(
            update={
                "availability_status": status,
                "location": location if location is not None else res.location,
            }
        )
        self._resources[resource_id] = updated
        return updated

