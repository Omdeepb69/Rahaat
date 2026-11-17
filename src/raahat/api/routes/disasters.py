"""Operations (disasters): the scope every report, incident and resource belongs to."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from raahat.api import scope
from raahat.api.deps import CurrentUser, get_db, require
from raahat.api.schemas import Coordinates, coordinates_or_none
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.security.jurisdiction import Jurisdiction, UnknownJurisdiction
from raahat.security.permissions import Permission

router = APIRouter(prefix="/disasters", tags=["operations"])

DISASTER_TYPES = ("flood", "cyclone", "landslide", "earthquake", "fire", "infrastructure", "other")

_SELECT = """
    SELECT d.id, d.name, d.disaster_type, d.status, d.description, d.area_name,
           d.state_code, d.district_code, d.is_standing, d.started_at, d.closed_at, d.created_at,
           ST_Y(d.map_center::geometry) AS lat, ST_X(d.map_center::geometry) AS lon,
           (SELECT count(*) FROM incidents i WHERE i.disaster_id = d.id
              AND i.status IN ('unverified','under_review','verified','assigned','in_progress')) AS open_incidents,
           (SELECT count(*) FROM resources r WHERE r.disaster_id = d.id AND NOT r.is_retired) AS resources
    FROM disasters d
"""


class DisasterResponse(BaseModel):
    id: uuid.UUID
    name: str
    disaster_type: str
    status: str
    description: Optional[str]
    area_name: Optional[str]
    state_code: Optional[str]
    district_code: Optional[str]
    jurisdiction: str
    is_standing: bool
    map_center: Optional[Coordinates]
    started_at: Optional[datetime]
    closed_at: Optional[datetime]
    created_at: datetime
    open_incidents: int
    resources: int


class CreateDisasterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=255)
    disaster_type: str
    description: Optional[str] = Field(default=None, max_length=2000)
    area_name: Optional[str] = Field(default=None, max_length=255)
    map_center: Optional[Coordinates] = None
    started_at: Optional[datetime] = None
    # LGD codes. Omitted fields default to the creator's own jurisdiction; a
    # state account may narrow to one of its districts.
    state_code: Optional[str] = Field(default=None, max_length=8)
    district_code: Optional[str] = Field(default=None, max_length=8)


class UpdateDisasterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    area_name: Optional[str] = Field(default=None, max_length=255)
    map_center: Optional[Coordinates] = None
    status: Optional[str] = Field(default=None, pattern="^(active|closed)$")


def _to_response(row) -> DisasterResponse:
    return DisasterResponse(
        id=row.id, name=row.name, disaster_type=row.disaster_type, status=row.status,
        description=row.description, area_name=row.area_name,
        state_code=row.state_code, district_code=row.district_code,
        jurisdiction=Jurisdiction(row.state_code, row.district_code).label if row.state_code
        else "No jurisdiction assigned",
        is_standing=row.is_standing,
        map_center=coordinates_or_none(row.lat, row.lon), started_at=row.started_at,
        closed_at=row.closed_at, created_at=row.created_at,
        open_incidents=row.open_incidents, resources=row.resources,
    )


def _validate_center(center: Optional[Coordinates]) -> Optional[str]:
    if center is None:
        return None
    if not (-90 <= center.latitude <= 90 and -180 <= center.longitude <= 180):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Map centre is out of range")
    return f"SRID=4326;POINT({center.longitude} {center.latitude})"


@router.get("", response_model=list[DisasterResponse], summary="List operations")
def list_disasters(
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|closed)$"),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> list[DisasterResponse]:
    condition, params = scope.of(session).sql("d")
    where = f" WHERE {condition}"
    if status_filter:
        where += " AND d.status = :status"
        params["status"] = status_filter
    rows = session.execute(
        text(f"{_SELECT}{where} ORDER BY (d.status = 'active') DESC, d.created_at DESC LIMIT 200"),
        params,
    ).all()
    return [_to_response(r) for r in rows]


@router.get("/{disaster_id}", response_model=DisasterResponse, summary="Get an operation")
def get_disaster(
    disaster_id: uuid.UUID,
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> DisasterResponse:
    scope.ensure_operation(session, disaster_id)
    row = session.execute(text(f"{_SELECT} WHERE d.id = :id"), {"id": disaster_id}).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Operation not found")
    return _to_response(row)


@router.post("", response_model=DisasterResponse, status_code=status.HTTP_201_CREATED,
             summary="Open an operation")
def create_disaster(
    body: CreateDisasterRequest,
    actor: CurrentUser = Depends(require(Permission.OPERATIONS_MANAGE)),
    session: Session = Depends(get_db),
) -> DisasterResponse:
    if body.disaster_type not in DISASTER_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Type must be one of: {', '.join(DISASTER_TYPES)}"
        )
    own = actor.jurisdiction
    try:
        target = Jurisdiction.validated(
            body.state_code or own.state_code, body.district_code or own.district_code
        )
    except UnknownJurisdiction as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    if not own.covers(target.state_code, target.district_code) or (
        own.district_code is not None and target.district_code != own.district_code
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That area is outside your jurisdiction")
    disaster = DisasterModel(
        id=uuid.uuid4(), name=body.name.strip(), disaster_type=body.disaster_type, status="active",
        description=(body.description or "").strip() or None,
        area_name=(body.area_name or "").strip() or None,
        map_center=_validate_center(body.map_center),
        started_at=body.started_at or datetime.now(timezone.utc),
        state_code=target.state_code, district_code=target.district_code,
    )
    session.add(disaster)
    session.flush()
    append_audit(
        session, action="operation.opened", actor_id=actor.id, entity_type="disaster",
        entity_id=disaster.id, disaster_id=disaster.id,
        payload={"name": disaster.name, "type": disaster.disaster_type,
                 "state_code": target.state_code, "district_code": target.district_code},
    )
    session.commit()
    return get_disaster(disaster.id, actor, session)


@router.patch("/{disaster_id}", response_model=DisasterResponse, summary="Update or close an operation")
def update_disaster(
    disaster_id: uuid.UUID,
    body: UpdateDisasterRequest,
    actor: CurrentUser = Depends(require(Permission.OPERATIONS_MANAGE)),
    session: Session = Depends(get_db),
) -> DisasterResponse:
    scope.ensure_operation(session, disaster_id)
    disaster = session.get(DisasterModel, disaster_id)
    if disaster is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Operation not found")
    changes: dict[str, object] = {}
    fields = body.model_dump(exclude_unset=True)
    for key in ("name", "description", "area_name"):
        if key in fields:
            value = (fields[key] or "").strip() or None
            if key == "name" and not value:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Name is required")
            if getattr(disaster, key) != value:
                changes[key] = {"from": getattr(disaster, key), "to": value}
                setattr(disaster, key, value)
    if "map_center" in fields:
        disaster.map_center = _validate_center(body.map_center)
        changes["map_center"] = fields["map_center"]
    if body.status and body.status != disaster.status:
        changes["status"] = {"from": disaster.status, "to": body.status}
        disaster.status = body.status
        disaster.closed_at = datetime.now(timezone.utc) if body.status == "closed" else None
    if changes:
        session.flush()
        append_audit(
            session, action="operation.updated", actor_id=actor.id, entity_type="disaster",
            entity_id=disaster.id, disaster_id=disaster.id, payload={"changes": changes},
        )
        session.commit()
    return get_disaster(disaster.id, actor, session)
