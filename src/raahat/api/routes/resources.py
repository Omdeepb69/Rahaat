"""Rescue resource register."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, get_db, require
from raahat.api.schemas import Coordinates, Page, Pagination, coordinates_or_none, split_csv
from raahat.application.resources import service as resources
from raahat.application.resources.service import ResourceError
from raahat.infrastructure.database.models.resource import RESOURCE_TYPES
from raahat.security.permissions import Permission

router = APIRouter(prefix="/resources", tags=["resources"])


class ResourcePosition(BaseModel):
    coordinates: Coordinates
    source: Optional[str]
    reported_at: datetime
    accuracy_m: Optional[float]


class CurrentAssignment(BaseModel):
    assignment_id: uuid.UUID
    incident_id: uuid.UUID
    incident_reference: str
    stage: str


class ResourceResponse(BaseModel):
    id: uuid.UUID
    disaster_id: uuid.UUID
    callsign: str
    resource_type: str
    name: str
    capacity: Optional[int]
    crew_size: Optional[int]
    declared_capabilities: list[str]
    capabilities: list[str]
    status: str
    status_note: Optional[str]
    base_name: Optional[str]
    contact: Optional[str]
    contact_redacted: bool
    notes: Optional[str]
    position: Optional[ResourcePosition]
    current_assignment: Optional[CurrentAssignment]
    is_retired: bool
    created_at: datetime
    updated_at: datetime


class ResourceOptions(BaseModel):
    types: list[str]
    capabilities: list[str]
    default_capabilities: dict[str, list[str]]
    manual_statuses: list[str]


class CreateResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    callsign: str = Field(min_length=2, max_length=64)
    resource_type: str
    name: str = Field(min_length=1, max_length=255)
    capacity: Optional[int] = Field(default=None, ge=0, le=10_000)
    crew_size: Optional[int] = Field(default=None, ge=0, le=1_000)
    capabilities: list[str] = Field(default_factory=list)
    base_name: Optional[str] = Field(default=None, max_length=255)
    contact: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=2000)


class UpdateResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=255)
    resource_type: Optional[str] = None
    capacity: Optional[int] = Field(default=None, ge=0, le=10_000)
    crew_size: Optional[int] = Field(default=None, ge=0, le=1_000)
    capabilities: Optional[list[str]] = None
    base_name: Optional[str] = Field(default=None, max_length=255)
    contact: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=2000)


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    note: Optional[str] = Field(default=None, max_length=500)


class PositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: str = Field(default="operator", pattern="^(operator|device_gps|integration)$")
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=100_000)
    reported_at: Optional[datetime] = None


class RetireRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


def _response(row: dict[str, Any], *, show_contact: bool) -> ResourceResponse:
    position = None
    coordinates = coordinates_or_none(row["latitude"], row["longitude"])
    if coordinates is not None and row["position_updated_at"] is not None:
        position = ResourcePosition(
            coordinates=coordinates, source=row["position_source"],
            reported_at=row["position_updated_at"], accuracy_m=row["position_accuracy_m"],
        )
    assignment = None
    if row["assignment_id"] is not None:
        assignment = CurrentAssignment(
            assignment_id=row["assignment_id"], incident_id=row["assigned_incident_id"],
            incident_reference=row["assigned_incident_reference"], stage=row["assignment_stage"],
        )
    declared = list(row["capabilities"] or [])
    return ResourceResponse(
        id=row["id"], disaster_id=row["disaster_id"], callsign=row["callsign"],
        resource_type=row["resource_type"], name=row["name"], capacity=row["capacity"],
        crew_size=row["crew_size"], declared_capabilities=declared,
        capabilities=resources.effective_capabilities(row["resource_type"], declared),
        status=row["availability_status"], status_note=row["status_note"],
        base_name=row["base_name"], contact=row["contact"] if show_contact else None,
        contact_redacted=bool(row["contact"]) and not show_contact, notes=row["notes"],
        position=position, current_assignment=assignment, is_retired=row["is_retired"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _can_see_contact(actor: CurrentUser) -> bool:
    return actor.can(Permission.RESOURCES_MANAGE) or actor.can(Permission.DISPATCH_DECIDE)


def _one(session: Session, resource_id: uuid.UUID, actor: CurrentUser) -> ResourceResponse:
    row = resources.get_resource_row(session, resource_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found")
    return _response(row, show_contact=_can_see_contact(actor))


def _run(session: Session, action) -> Any:
    try:
        result = action()
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ResourceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    session.commit()
    return result


@router.get("/options", response_model=ResourceOptions, summary="Resource types and capabilities")
def options(_: CurrentUser = Depends(require(Permission.RESOURCES_READ))) -> ResourceOptions:
    return ResourceOptions(
        types=list(RESOURCE_TYPES),
        capabilities=sorted(resources.KNOWN_CAPABILITIES),
        default_capabilities={k: list(v) for k, v in resources.DEFAULT_CAPABILITIES.items()},
        manual_statuses=sorted(resources.MANUAL_STATUSES),
    )


@router.get("", response_model=Page[ResourceResponse], summary="List resources")
def list_resources(
    disaster_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status", description="Comma-separated statuses"),
    resource_type: Optional[str] = Query(None, alias="type", description="Comma-separated types"),
    q: Optional[str] = Query(None, max_length=120),
    include_retired: bool = Query(False),
    page: Pagination = Depends(),
    actor: CurrentUser = Depends(require(Permission.RESOURCES_READ)),
    session: Session = Depends(get_db),
) -> Page[ResourceResponse]:
    rows, total = resources.list_resources(
        session, disaster_id=disaster_id, statuses=split_csv(status_filter),
        types=split_csv(resource_type), search=q, include_retired=include_retired,
        limit=page.limit, offset=page.offset,
    )
    show = _can_see_contact(actor)
    return Page(
        items=[_response(r, show_contact=show) for r in rows], total=total,
        limit=page.limit, offset=page.offset,
    )


@router.get("/{resource_id}", response_model=ResourceResponse, summary="Get a resource")
def get_resource(
    resource_id: uuid.UUID,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_READ)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    return _one(session, resource_id, actor)


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED,
             summary="Register a resource")
def create_resource(
    body: CreateResourceRequest,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_MANAGE)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    created = _run(session, lambda: resources.create_resource(session, actor_id=actor.id, **body.model_dump()))
    return _one(session, created.id, actor)


@router.patch("/{resource_id}", response_model=ResourceResponse, summary="Edit a resource")
def update_resource(
    resource_id: uuid.UUID,
    body: UpdateResourceRequest,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_MANAGE)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    _run(
        session,
        lambda: resources.update_resource(
            session, resource_id=resource_id, actor_id=actor.id,
            fields=body.model_dump(exclude_unset=True),
        ),
    )
    return _one(session, resource_id, actor)


@router.post("/{resource_id}/status", response_model=ResourceResponse, summary="Change availability")
def set_status(
    resource_id: uuid.UUID,
    body: StatusRequest,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_MANAGE)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    _run(
        session,
        lambda: resources.set_status(
            session, resource_id=resource_id, actor_id=actor.id, status=body.status, note=body.note
        ),
    )
    return _one(session, resource_id, actor)


@router.put("/{resource_id}/position", response_model=ResourceResponse, summary="Report a position")
def update_position(
    resource_id: uuid.UUID,
    body: PositionRequest,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_MANAGE)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    _run(
        session,
        lambda: resources.update_position(
            session, resource_id=resource_id, actor_id=actor.id, latitude=body.latitude,
            longitude=body.longitude, source=body.source, accuracy_m=body.accuracy_m,
            reported_at=body.reported_at,
        ),
    )
    return _one(session, resource_id, actor)


@router.post("/{resource_id}/retire", response_model=ResourceResponse, summary="Retire a resource")
def retire(
    resource_id: uuid.UUID,
    body: RetireRequest,
    actor: CurrentUser = Depends(require(Permission.RESOURCES_MANAGE)),
    session: Session = Depends(get_db),
) -> ResourceResponse:
    _run(session, lambda: resources.retire(session, resource_id=resource_id, actor_id=actor.id, reason=body.reason))
    return _one(session, resource_id, actor)
