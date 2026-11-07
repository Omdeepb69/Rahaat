"""Resource registry and availability management API routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from raahat.api.dependencies import (
    get_resource_service,
    get_session_factory,
    require_dispatcher_id,
)
from raahat.application.resources import ResourceService
from raahat.domain.operations.operation import Resource
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import ResourceStatus, ResourceType

router = APIRouter(prefix="/resources", tags=["resources"])


class RegisterResourceRequest(BaseModel):
    """Payload to register a physical or human rescue resource."""

    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    resource_type: ResourceType
    name: str = Field(..., min_length=1, max_length=255, description="Asset or team name")
    capacity: Optional[int] = Field(default=None, ge=1, description="Rescue or shelter capacity")
    availability_status: ResourceStatus = ResourceStatus.AVAILABLE
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)


class UpdateResourceStatusRequest(BaseModel):
    """Payload to update the availability status and coordinates of a resource."""

    model_config = ConfigDict(extra="forbid")

    availability_status: ResourceStatus
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    reason: Optional[str] = Field(default=None, description="Operational justification")


class ResourceResponse(BaseModel):
    """Resource response representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID
    disaster_id: uuid.UUID
    resource_type: ResourceType
    name: str
    capacity: Optional[int]
    availability_status: ResourceStatus
    location: Optional[PointCoordinates]
    distance_meters: Optional[float] = None
    created_at: datetime


def _to_response(resource: Resource, distance_meters: Optional[float] = None) -> ResourceResponse:
    return ResourceResponse(
        id=resource.id,
        disaster_id=resource.disaster_id,
        resource_type=resource.resource_type,
        name=resource.name,
        capacity=resource.capacity,
        availability_status=resource.availability_status,
        location=resource.location,
        distance_meters=distance_meters,
        created_at=resource.created_at,
    )


@router.post(
    "",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a disaster rescue resource",
)
def register_resource(
    payload: RegisterResourceRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    """Register a new rescue asset with authenticated dispatcher authorization."""
    location: Optional[PointCoordinates] = None
    if payload.latitude is not None and payload.longitude is not None:
        location = PointCoordinates(latitude=payload.latitude, longitude=payload.longitude)

    resource = service.register_resource(
        disaster_id=payload.disaster_id,
        resource_type=payload.resource_type,
        name=payload.name,
        capacity=payload.capacity,
        availability_status=payload.availability_status,
        location=location,
        registered_by=dispatcher_id,
    )
    return _to_response(resource)


@router.get(
    "",
    response_model=list[ResourceResponse],
    status_code=status.HTTP_200_OK,
    summary="Query resources with optional spatial proximity filtering",
)
def list_resources(
    disaster_id: Optional[uuid.UUID] = Query(None, description="Target disaster ID"),
    resource_type: Optional[ResourceType] = Query(None, description="Filter by asset type"),
    resource_status: Optional[ResourceStatus] = Query(None, alias="status", description="Filter by availability status"),
    lat: Optional[float] = Query(None, ge=-90.0, le=90.0, description="Query latitude for proximity search"),
    lon: Optional[float] = Query(None, ge=-180.0, le=180.0, description="Query longitude for proximity search"),
    radius_meters: Optional[float] = Query(None, gt=0, description="Search radius in meters"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    session_factory=Depends(get_session_factory),
    service: ResourceService = Depends(get_resource_service),
) -> list[ResourceResponse]:
    """Query resources. If lat, lon, and radius_meters are provided, performs PostGIS spatial search."""
    target_disaster_id = disaster_id
    if target_disaster_id is None:
        with session_factory() as session:
            from raahat.infrastructure.database.models.disaster import DisasterModel

            latest = session.scalars(
                select(DisasterModel).order_by(DisasterModel.created_at.desc()).limit(1)
            ).first()
            if latest:
                target_disaster_id = latest.id

    if target_disaster_id is None:
        return []

    if lat is not None and lon is not None and radius_meters is not None:
        coords = PointCoordinates(latitude=lat, longitude=lon)
        nearby = service.find_nearby_resources(
            disaster_id=target_disaster_id,
            coordinates=coords,
            radius_meters=radius_meters,
            resource_type=resource_type,
            status=resource_status,
            limit=limit,
        )
        return [_to_response(item.resource, distance_meters=item.distance_meters) for item in nearby]

    resources = service.list_resources(
        disaster_id=target_disaster_id,
        resource_type=resource_type,
        status=resource_status,
    )
    return [_to_response(r) for r in resources]


@router.get(
    "/{resource_id}",
    response_model=ResourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Get resource by ID",
)
def get_resource(
    resource_id: uuid.UUID,
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    """Retrieve details of a specific rescue resource."""
    resource = service.get_resource(resource_id)
    if resource is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_id} not found",
        )
    return _to_response(resource)


@router.patch(
    "/{resource_id}/status",
    response_model=ResourceResponse,
    status_code=status.HTTP_200_OK,
    summary="Update resource availability status and location",
)
def update_resource_status(
    resource_id: uuid.UUID,
    payload: UpdateResourceStatusRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: ResourceService = Depends(get_resource_service),
) -> ResourceResponse:
    """Update resource availability status and GPS pin with dispatcher authorization and audit logging."""
    location: Optional[PointCoordinates] = None
    if payload.latitude is not None and payload.longitude is not None:
        location = PointCoordinates(latitude=payload.latitude, longitude=payload.longitude)

    try:
        updated = service.update_resource_status(
            resource_id=resource_id,
            status=payload.availability_status,
            location=location,
            updated_by=dispatcher_id,
            reason=payload.reason,
        )
        return _to_response(updated)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

