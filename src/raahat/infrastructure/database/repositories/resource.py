"""PostgreSQL + PostGIS implementation of ResourceRepository."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from geoalchemy2.elements import WKTElement
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.operations.operation import Resource
from raahat.domain.resources.repository import ResourceRepository
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import ResourceStatus, ResourceType
from raahat.infrastructure.database.models.resource import ResourceModel
from raahat.infrastructure.database.repositories.location_hypothesis import parse_wkb_point

logger = logging.getLogger(__name__)

_NEARBY_RESOURCES_SQL = text(
    """
    SELECT
        id,
        disaster_id,
        resource_type,
        name,
        capacity,
        availability_status,
        ST_X(location::geometry) AS longitude,
        ST_Y(location::geometry) AS latitude,
        created_at,
        ST_Distance(location, ST_MakePoint(:lon, :lat)::geography) AS distance_m
    FROM resources
    WHERE
        disaster_id = :disaster_id
        AND location IS NOT NULL
        AND ST_DWithin(location, ST_MakePoint(:lon, :lat)::geography, :radius_m)
        AND (cast(:type_filter as text) IS NULL OR resource_type = cast(:type_filter as text))
        AND (cast(:status_filter as text) IS NULL OR availability_status = cast(:status_filter as text))
    ORDER BY distance_m ASC
    LIMIT :max_results
    """
)


def _model_to_resource(model: ResourceModel) -> Resource:
    """Convert an ORM ResourceModel to a frozen domain Resource entity."""
    coords: Optional[PointCoordinates] = None
    if model.location is not None:
        try:
            coords = parse_wkb_point(model.location)
        except Exception as exc:
            logger.warning("Failed to parse resource location geometry: %s", exc)

    return Resource(
        id=model.id,
        disaster_id=model.disaster_id,
        resource_type=ResourceType(model.resource_type),
        name=model.name,
        capacity=model.capacity,
        availability_status=ResourceStatus(model.availability_status),
        location=coords,
        created_at=model.created_at,
    )


class PostgresResourceRepository(ResourceRepository):
    """PostgreSQL + PostGIS repository managing physical and human rescue resources."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(
        self,
        resource: Resource,
        session: Optional[Session] = None,
    ) -> Resource:
        if session is not None:
            return self._save_with_session(resource, session)
        with self._session_factory() as new_session:
            saved = self._save_with_session(resource, new_session)
            new_session.commit()
            return saved

    def _save_with_session(self, resource: Resource, session: Session) -> Resource:
        geom = (
            WKTElement(
                f"POINT({resource.location.longitude} {resource.location.latitude})",
                srid=4326,
            )
            if resource.location is not None
            else None
        )

        model = session.get(ResourceModel, resource.id)
        if model is None:
            model = ResourceModel(
                id=resource.id,
                disaster_id=resource.disaster_id,
                resource_type=resource.resource_type.value,
                name=resource.name,
                capacity=resource.capacity,
                availability_status=resource.availability_status.value,
                location=geom,
            )
            session.add(model)
        else:
            model.disaster_id = resource.disaster_id
            model.resource_type = resource.resource_type.value
            model.name = resource.name
            model.capacity = resource.capacity
            model.availability_status = resource.availability_status.value
            model.location = geom

        session.flush()
        return _model_to_resource(model)

    def get_by_id(
        self,
        resource_id: uuid.UUID,
        session: Optional[Session] = None,
    ) -> Optional[Resource]:
        if session is not None:
            model = session.get(ResourceModel, resource_id)
            return _model_to_resource(model) if model else None
        with self._session_factory() as new_session:
            model = new_session.get(ResourceModel, resource_id)
            return _model_to_resource(model) if model else None

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        session: Optional[Session] = None,
    ) -> list[Resource]:
        if session is not None:
            return self._list_by_disaster_with_session(disaster_id, resource_type, status, session)
        with self._session_factory() as new_session:
            return self._list_by_disaster_with_session(disaster_id, resource_type, status, new_session)

    def _list_by_disaster_with_session(
        self,
        disaster_id: uuid.UUID,
        resource_type: Optional[ResourceType],
        status: Optional[ResourceStatus],
        session: Session,
    ) -> list[Resource]:
        stmt = select(ResourceModel).where(ResourceModel.disaster_id == disaster_id)
        if resource_type is not None:
            stmt = stmt.where(ResourceModel.resource_type == resource_type.value)
        if status is not None:
            stmt = stmt.where(ResourceModel.availability_status == status.value)
        stmt = stmt.order_by(ResourceModel.created_at.asc())

        models = session.scalars(stmt).all()
        return [_model_to_resource(m) for m in models]

    def find_nearby(
        self,
        disaster_id: uuid.UUID,
        coordinates: PointCoordinates,
        radius_meters: float,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
        limit: int = 50,
        session: Optional[Session] = None,
    ) -> list[tuple[Resource, float]]:
        if session is not None:
            return self._find_nearby_with_session(
                disaster_id, coordinates, radius_meters, resource_type, status, limit, session
            )
        with self._session_factory() as new_session:
            return self._find_nearby_with_session(
                disaster_id, coordinates, radius_meters, resource_type, status, limit, new_session
            )

    def _find_nearby_with_session(
        self,
        disaster_id: uuid.UUID,
        coordinates: PointCoordinates,
        radius_meters: float,
        resource_type: Optional[ResourceType],
        status: Optional[ResourceStatus],
        limit: int,
        session: Session,
    ) -> list[tuple[Resource, float]]:
        params = {
            "disaster_id": disaster_id,
            "lon": coordinates.longitude,
            "lat": coordinates.latitude,
            "radius_m": float(radius_meters),
            "type_filter": resource_type.value if resource_type else None,
            "status_filter": status.value if status else None,
            "max_results": limit,
        }
        result = session.execute(_NEARBY_RESOURCES_SQL, params)
        rows = result.fetchall()

        matched: list[tuple[Resource, float]] = []
        for row in rows:
            loc = (
                PointCoordinates(
                    latitude=float(row.latitude),
                    longitude=float(row.longitude),
                )
                if row.latitude is not None and row.longitude is not None
                else None
            )
            res = Resource(
                id=uuid.UUID(str(row.id)),
                disaster_id=uuid.UUID(str(row.disaster_id)),
                resource_type=ResourceType(row.resource_type),
                name=row.name,
                capacity=row.capacity,
                availability_status=ResourceStatus(row.availability_status),
                location=loc,
                created_at=row.created_at,
            )
            matched.append((res, float(row.distance_m)))
        return matched

    def update_status(
        self,
        resource_id: uuid.UUID,
        status: ResourceStatus,
        location: Optional[PointCoordinates] = None,
        session: Optional[Session] = None,
    ) -> Optional[Resource]:
        if session is not None:
            return self._update_status_with_session(resource_id, status, location, session)
        with self._session_factory() as new_session:
            updated = self._update_status_with_session(resource_id, status, location, new_session)
            new_session.commit()
            return updated

    def _update_status_with_session(
        self,
        resource_id: uuid.UUID,
        status: ResourceStatus,
        location: Optional[PointCoordinates],
        session: Session,
    ) -> Optional[Resource]:
        model = session.get(ResourceModel, resource_id)
        if model is None:
            return None

        model.availability_status = status.value
        if location is not None:
            model.location = WKTElement(
                f"POINT({location.longitude} {location.latitude})",
                srid=4326,
            )
        session.flush()
        return _model_to_resource(model)

