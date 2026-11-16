"""Location hypotheses for incidents: recording, confirming, rejecting, and
keeping the incident's "best current position" in step.

A hypothesis is one piece of evidence about where an incident is, with its
source. The incident row carries a denormalised copy of the best one so lists
and the map can be served without a join per incident. That copy is recomputed
here whenever hypotheses change, by one rule:

1. a confirmed hypothesis wins (latest confirmation);
2. otherwise the best unrejected candidate by source strength
   (device position > operator entry > geocoder > landmark match), then score;
3. otherwise the incident has no position.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from raahat.domain.shared.enums import LocationSource
from raahat.infrastructure.database.models.incident import IncidentModel
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.repositories.audit import append_audit

# Radius drawn around a landmark-derived candidate. "Near the bridge" does not
# say how near, so this is a stated assumption, not a measurement.
ASSUMED_LANDMARK_RADIUS_M = {"at": 150.0, "near": 300.0, "behind": 300.0, "opposite": 300.0, "in_front_of": 300.0}
DEFAULT_LANDMARK_RADIUS_M = 400.0

_SOURCE_RANK = {
    LocationSource.CALLER_GPS.value: 4,
    LocationSource.OPERATOR.value: 3,
    LocationSource.GEOCODER.value: 2,
    LocationSource.LANDMARK.value: 1,
    LocationSource.UNKNOWN.value: 0,
}


class LocationError(ValueError):
    pass


@dataclass(frozen=True)
class HypothesisView:
    id: uuid.UUID
    incident_id: uuid.UUID
    latitude: float
    longitude: float
    label: Optional[str]
    source: str
    source_detail: dict[str, Any]
    score: Optional[float]
    uncertainty_radius_m: Optional[float]
    verification_status: str
    report_id: Optional[uuid.UUID]
    confirmed_by: Optional[uuid.UUID]
    confirmed_at: Optional[datetime]
    created_at: datetime


_LIST = text(
    """
    SELECT id, incident_id, candidate_label, source, source_detail, probability,
           uncertainty_radius_m, verification_status, report_id, confirmed_by, confirmed_at,
           created_at, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon
    FROM location_hypotheses
    WHERE incident_id = :incident_id
    ORDER BY created_at ASC, id ASC
    """
)


def validate_coordinates(latitude: float, longitude: float) -> None:
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        raise LocationError("Coordinates are out of range")
    if latitude == 0.0 and longitude == 0.0:
        raise LocationError("Coordinates 0,0 are not a valid position")


def list_hypotheses(session: Session, incident_id: uuid.UUID) -> list[HypothesisView]:
    rows = session.execute(_LIST, {"incident_id": incident_id}).all()
    return [
        HypothesisView(
            id=r.id,
            incident_id=r.incident_id,
            latitude=float(r.lat),
            longitude=float(r.lon),
            label=r.candidate_label,
            source=r.source,
            source_detail=r.source_detail or {},
            score=float(r.probability) if r.probability is not None else None,
            uncertainty_radius_m=r.uncertainty_radius_m,
            verification_status=r.verification_status,
            report_id=r.report_id,
            confirmed_by=r.confirmed_by,
            confirmed_at=r.confirmed_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


def add_hypothesis(
    session: Session,
    *,
    incident_id: uuid.UUID,
    latitude: float,
    longitude: float,
    source: LocationSource,
    label: Optional[str],
    source_detail: Optional[dict[str, Any]] = None,
    score: Optional[float] = None,
    uncertainty_radius_m: Optional[float] = None,
    report_id: Optional[uuid.UUID] = None,
    verification_status: str = "candidate",
) -> uuid.UUID:
    """Record a candidate position. Does not refresh the incident; call ``refresh_incident_location``."""
    validate_coordinates(latitude, longitude)
    if score is not None and not 0.0 <= score <= 1.0:
        raise LocationError("Score must be between 0 and 1")
    hypothesis = LocationHypothesisModel(
        id=uuid.uuid4(),
        incident_id=incident_id,
        location=f"SRID=4326;POINT({longitude} {latitude})",
        candidate_label=(label or None) and label[:255],
        probability=score,
        uncertainty_radius_m=uncertainty_radius_m,
        verification_status=verification_status,
        source=source.value,
        source_detail=source_detail or {},
        report_id=report_id,
    )
    session.add(hypothesis)
    session.flush()
    return hypothesis.id


def refresh_incident_location(session: Session, incident: IncidentModel) -> None:
    """Recompute the incident's denormalised best position from its hypotheses."""
    views = [v for v in list_hypotheses(session, incident.id) if v.verification_status != "rejected"]
    confirmed = [v for v in views if v.verification_status == "confirmed"]
    chosen: Optional[HypothesisView]
    if confirmed:
        chosen = max(confirmed, key=lambda v: v.confirmed_at or v.created_at)
        status = "confirmed"
    elif views:
        chosen = max(
            views,
            key=lambda v: (_SOURCE_RANK.get(v.source, 0), v.score or 0.0, -v.created_at.timestamp()),
        )
        status = "candidate"
    else:
        chosen, status = None, "none"

    if chosen is None:
        incident.location = None
        incident.location_source = None
        incident.location_label = None
        incident.location_confidence = None
        incident.location_uncertainty_m = None
        incident.location_hypothesis_id = None
    else:
        incident.location = f"SRID=4326;POINT({chosen.longitude} {chosen.latitude})"
        incident.location_source = chosen.source
        incident.location_label = chosen.label
        incident.location_confidence = chosen.score
        incident.location_uncertainty_m = chosen.uncertainty_radius_m
        incident.location_hypothesis_id = chosen.id
    incident.location_status = status
    session.flush()


def _get_incident(session: Session, incident_id: uuid.UUID) -> IncidentModel:
    incident = session.get(IncidentModel, incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    return incident


def confirm_hypothesis(
    session: Session, *, incident_id: uuid.UUID, hypothesis_id: uuid.UUID, actor_id: uuid.UUID,
    note: Optional[str] = None,
) -> None:
    """Mark one existing candidate as the operator-confirmed position."""
    incident = _get_incident(session, incident_id)
    hypothesis = session.get(LocationHypothesisModel, hypothesis_id)
    if hypothesis is None or hypothesis.incident_id != incident_id:
        raise LookupError("Location candidate not found for this incident")
    now = datetime.now(timezone.utc)
    # Only one confirmed position at a time: earlier confirmations become stale.
    for other in session.execute(
        select(LocationHypothesisModel).where(
            LocationHypothesisModel.incident_id == incident_id,
            LocationHypothesisModel.verification_status == "confirmed",
            LocationHypothesisModel.id != hypothesis_id,
        )
    ).scalars():
        other.verification_status = "stale"
    hypothesis.verification_status = "confirmed"
    hypothesis.confirmed_by = actor_id
    hypothesis.confirmed_at = now
    session.flush()
    refresh_incident_location(session, incident)
    append_audit(
        session,
        action="incident.location_confirmed",
        actor_id=actor_id,
        entity_type="incident",
        entity_id=incident_id,
        disaster_id=incident.disaster_id,
        payload={
            "hypothesis_id": str(hypothesis_id),
            "source": hypothesis.source,
            "label": hypothesis.candidate_label,
            "note": note,
        },
    )


def set_operator_location(
    session: Session,
    *,
    incident_id: uuid.UUID,
    latitude: float,
    longitude: float,
    actor_id: uuid.UUID,
    label: Optional[str] = None,
    uncertainty_radius_m: Optional[float] = None,
    note: Optional[str] = None,
) -> uuid.UUID:
    """Record a position entered by an operator and confirm it."""
    incident = _get_incident(session, incident_id)
    hypothesis_id = add_hypothesis(
        session,
        incident_id=incident_id,
        latitude=latitude,
        longitude=longitude,
        source=LocationSource.OPERATOR,
        label=label or "Position set by operator",
        source_detail={"entered_by": str(actor_id)},
        uncertainty_radius_m=uncertainty_radius_m,
    )
    confirm_hypothesis(
        session, incident_id=incident.id, hypothesis_id=hypothesis_id, actor_id=actor_id, note=note
    )
    return hypothesis_id


def reject_hypothesis(
    session: Session, *, incident_id: uuid.UUID, hypothesis_id: uuid.UUID, actor_id: uuid.UUID,
    reason: Optional[str] = None,
) -> None:
    incident = _get_incident(session, incident_id)
    hypothesis = session.get(LocationHypothesisModel, hypothesis_id)
    if hypothesis is None or hypothesis.incident_id != incident_id:
        raise LookupError("Location candidate not found for this incident")
    hypothesis.verification_status = "rejected"
    session.flush()
    refresh_incident_location(session, incident)
    append_audit(
        session,
        action="incident.location_rejected",
        actor_id=actor_id,
        entity_type="incident",
        entity_id=incident_id,
        disaster_id=incident.disaster_id,
        payload={"hypothesis_id": str(hypothesis_id), "label": hypothesis.candidate_label, "reason": reason},
    )
