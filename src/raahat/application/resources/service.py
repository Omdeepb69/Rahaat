"""Rescue resource register: records, availability and last known position.

Resources exist only because an authorised person entered them or an
integration reported them. Every change is audited. A position is always
stored with its source and the time it was reported.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.operation import AssignmentModel
from raahat.infrastructure.database.models.resource import (
    POSITION_SOURCES,
    RESOURCE_TYPES,
    ResourceModel,
)
from raahat.infrastructure.database.repositories.audit import append_audit

# What each resource type can do unless its record says otherwise.
DEFAULT_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "boat": ("water_rescue", "evacuation"),
    "ambulance": ("medical", "patient_transport"),
    "medical_team": ("medical",),
    "rescue_team": ("search_rescue", "evacuation"),
    "vehicle": ("evacuation", "relief_supply"),
    "helicopter": ("air_rescue", "water_rescue", "evacuation"),
    "shelter": ("shelter",),
    "other": (),
}
KNOWN_CAPABILITIES = frozenset(
    {
        "water_rescue", "evacuation", "medical", "patient_transport", "search_rescue",
        "relief_supply", "air_rescue", "shelter", "heavy_lifting", "communications",
    }
)
# Statuses a person may set. 'assigned' is set only by an approved dispatch decision.
MANUAL_STATUSES = frozenset({"available", "maintenance", "offline"})
_CALLSIGN = re.compile(r"^[A-Z0-9][A-Z0-9 ._/-]{1,63}$")


class ResourceError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def effective_capabilities(resource_type: str, declared: Sequence[str]) -> list[str]:
    """Declared capabilities if any were entered, otherwise the type's defaults."""
    if declared:
        return sorted(set(declared))
    return sorted(DEFAULT_CAPABILITIES.get(resource_type, ()))


_SELECT = """
    SELECT r.id, r.disaster_id, r.callsign, r.resource_type, r.name, r.capacity, r.crew_size,
           r.capabilities, r.availability_status, r.status_note, r.base_name, r.contact, r.notes,
           ST_Y(r.location::geometry) AS latitude, ST_X(r.location::geometry) AS longitude,
           r.position_source, r.position_updated_at, r.position_accuracy_m, r.is_retired,
           r.created_at, r.updated_at,
           a.id AS assignment_id, a.incident_id AS assigned_incident_id, a.stage AS assignment_stage,
           i.reference AS assigned_incident_reference
    FROM resources r
    LEFT JOIN assignments a ON a.resource_id = r.id AND a.status = 'approved'
    LEFT JOIN incidents i ON i.id = a.incident_id
"""


def list_resources(
    session: Session,
    *,
    disaster_id: Optional[uuid.UUID] = None,
    statuses: Sequence[str] = (),
    types: Sequence[str] = (),
    search: Optional[str] = None,
    include_retired: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["TRUE"]
    params: dict[str, Any] = {}
    if disaster_id is not None:
        clauses.append("r.disaster_id = :disaster_id")
        params["disaster_id"] = disaster_id
    if not include_retired:
        clauses.append("r.is_retired = FALSE")
    for name, values, column in (
        ("status", statuses, "r.availability_status"),
        ("type", types, "r.resource_type"),
    ):
        if values:
            keys = []
            for index, value in enumerate(values):
                params[f"{name}_{index}"] = value
                keys.append(f":{name}_{index}")
            clauses.append(f"{column} IN ({', '.join(keys)})")
    if search:
        clauses.append("(r.callsign ILIKE :search OR r.name ILIKE :search OR r.base_name ILIKE :search)")
        params["search"] = f"%{search.strip()}%"
    where = " WHERE " + " AND ".join(clauses)
    total = session.execute(text(f"SELECT count(*) FROM resources r{where}"), params).scalar_one()
    rows = session.execute(
        text(f"{_SELECT}{where} ORDER BY r.callsign, r.id LIMIT :limit OFFSET :offset"),
        {**params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows], total


def get_resource_row(session: Session, resource_id: uuid.UUID) -> Optional[dict[str, Any]]:
    row = session.execute(text(f"{_SELECT} WHERE r.id = :id"), {"id": resource_id}).mappings().first()
    return dict(row) if row else None


def _validate_common(
    *, resource_type: Optional[str], capacity: Optional[int], crew_size: Optional[int],
    capabilities: Optional[Sequence[str]],
) -> None:
    if resource_type is not None and resource_type not in RESOURCE_TYPES:
        raise ResourceError("Unknown resource type")
    if capacity is not None and not 0 <= capacity <= 10_000:
        raise ResourceError("Capacity is out of range")
    if crew_size is not None and not 0 <= crew_size <= 1_000:
        raise ResourceError("Crew size is out of range")
    if capabilities is not None:
        unknown = sorted(set(capabilities) - KNOWN_CAPABILITIES)
        if unknown:
            raise ResourceError(f"Unknown capability: {', '.join(unknown)}")


def create_resource(
    session: Session,
    *,
    disaster_id: uuid.UUID,
    actor_id: uuid.UUID,
    callsign: str,
    resource_type: str,
    name: str,
    capacity: Optional[int] = None,
    crew_size: Optional[int] = None,
    capabilities: Sequence[str] = (),
    base_name: Optional[str] = None,
    contact: Optional[str] = None,
    notes: Optional[str] = None,
) -> ResourceModel:
    if session.get(DisasterModel, disaster_id) is None:
        raise LookupError("Operation not found")
    callsign = callsign.strip().upper()
    if not _CALLSIGN.match(callsign):
        raise ResourceError("Callsign must be 2-64 characters: letters, digits, space . _ / -")
    if not name.strip():
        raise ResourceError("Name is required")
    _validate_common(
        resource_type=resource_type, capacity=capacity, crew_size=crew_size, capabilities=capabilities
    )
    resource = ResourceModel(
        id=uuid.uuid4(),
        disaster_id=disaster_id,
        callsign=callsign,
        resource_type=resource_type,
        name=name.strip(),
        capacity=capacity,
        crew_size=crew_size,
        capabilities=sorted(set(capabilities)),
        base_name=(base_name or "").strip() or None,
        contact=(contact or "").strip() or None,
        notes=(notes or "").strip() or None,
        availability_status="available",
        created_by=actor_id,
    )
    session.add(resource)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ResourceError(f"Callsign '{callsign}' is already in use in this operation") from exc
    append_audit(
        session,
        action="resource.registered",
        actor_id=actor_id,
        entity_type="resource",
        entity_id=resource.id,
        disaster_id=disaster_id,
        payload={"callsign": callsign, "type": resource_type, "capacity": capacity},
    )
    return resource


def _locked(session: Session, resource_id: uuid.UUID) -> ResourceModel:
    resource = session.get(ResourceModel, resource_id, with_for_update=True)
    if resource is None:
        raise LookupError("Resource not found")
    return resource


def update_resource(
    session: Session, *, resource_id: uuid.UUID, actor_id: uuid.UUID, fields: dict[str, Any]
) -> ResourceModel:
    resource = _locked(session, resource_id)
    _validate_common(
        resource_type=fields.get("resource_type"),
        capacity=fields.get("capacity"),
        crew_size=fields.get("crew_size"),
        capabilities=fields.get("capabilities"),
    )
    changes: dict[str, Any] = {}
    for key in ("name", "resource_type", "capacity", "crew_size", "capabilities", "base_name", "contact", "notes"):
        if key not in fields:
            continue
        value = fields[key]
        if isinstance(value, str):
            value = value.strip() or None
        if key == "capabilities" and value is not None:
            value = sorted(set(value))
        if key in ("name", "resource_type") and not value:
            raise ResourceError(f"{key.replace('_', ' ').capitalize()} is required")
        if getattr(resource, key) != value:
            # Contact details are not copied into the audit trail.
            changes[key] = "changed" if key == "contact" else {"from": getattr(resource, key), "to": value}
            setattr(resource, key, value)
    if changes:
        resource.updated_at = _now()
        session.flush()
        append_audit(
            session,
            action="resource.updated",
            actor_id=actor_id,
            entity_type="resource",
            entity_id=resource.id,
            disaster_id=resource.disaster_id,
            payload={"callsign": resource.callsign, "changes": changes},
        )
    return resource


def set_status(
    session: Session, *, resource_id: uuid.UUID, actor_id: uuid.UUID, status: str,
    note: Optional[str] = None,
) -> ResourceModel:
    resource = _locked(session, resource_id)
    if status not in MANUAL_STATUSES:
        raise ResourceError(
            "Status must be available, maintenance or offline. A resource becomes "
            "'assigned' only through an approved dispatch decision."
        )
    active = session.execute(
        select(AssignmentModel.id).where(
            AssignmentModel.resource_id == resource_id, AssignmentModel.status == "approved"
        )
    ).first()
    if active:
        raise ResourceError(
            "This resource is committed to an incident. Complete or cancel that assignment first."
        )
    if status != "available" and not (note and note.strip()):
        raise ResourceError("A note is required when taking a resource out of service")
    previous = resource.availability_status
    if previous == status and (note or None) == resource.status_note:
        return resource
    resource.availability_status = status
    resource.status_note = (note or "").strip() or None
    resource.updated_at = _now()
    session.flush()
    append_audit(
        session,
        action="resource.status_changed",
        actor_id=actor_id,
        entity_type="resource",
        entity_id=resource.id,
        disaster_id=resource.disaster_id,
        payload={"callsign": resource.callsign, "from": previous, "to": status, "note": note},
    )
    return resource


def update_position(
    session: Session,
    *,
    resource_id: uuid.UUID,
    actor_id: Optional[uuid.UUID],
    latitude: float,
    longitude: float,
    source: str,
    accuracy_m: Optional[float] = None,
    reported_at: Optional[datetime] = None,
) -> ResourceModel:
    resource = _locked(session, resource_id)
    if source not in POSITION_SOURCES:
        raise ResourceError("Position source must be operator, device_gps or integration")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
        raise ResourceError("Coordinates are out of range")
    now = _now()
    when = reported_at or now
    if when > now:
        raise ResourceError("Position time cannot be in the future")
    resource.location = f"SRID=4326;POINT({longitude} {latitude})"
    resource.position_source = source
    resource.position_updated_at = when
    resource.position_accuracy_m = accuracy_m
    resource.updated_at = now
    session.flush()
    append_audit(
        session,
        action="resource.position_updated",
        actor_id=actor_id,
        entity_type="resource",
        entity_id=resource.id,
        disaster_id=resource.disaster_id,
        payload={
            "callsign": resource.callsign,
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "source": source,
            "reported_at": when.isoformat(),
        },
    )
    return resource


def retire(session: Session, *, resource_id: uuid.UUID, actor_id: uuid.UUID, reason: str) -> ResourceModel:
    """Remove a resource from use while keeping its history."""
    resource = _locked(session, resource_id)
    if not reason.strip():
        raise ResourceError("A reason is required")
    if resource.availability_status == "assigned":
        raise ResourceError("This resource is committed to an incident")
    resource.is_retired = True
    resource.availability_status = "offline"
    resource.status_note = reason.strip()
    resource.updated_at = _now()
    session.flush()
    append_audit(
        session,
        action="resource.retired",
        actor_id=actor_id,
        entity_type="resource",
        entity_id=resource.id,
        disaster_id=resource.disaster_id,
        payload={"callsign": resource.callsign, "reason": reason.strip()},
    )
    return resource
