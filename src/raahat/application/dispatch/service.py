"""Dispatch: recommendations, human decisions and assignment progress.

Nothing here commits a resource without a named person approving it. The
recommendation engine only reads. A decision records what the engine suggested
at that moment, what the person chose, and why.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raahat.application.ai.registry import Providers
from raahat.application.dispatch import recommender
from raahat.application.dispatch.priority import PriorityScore, score_incident
from raahat.application.resources.service import effective_capabilities
from raahat.domain.incidents.lifecycle import DISPATCHABLE_STATUSES
from raahat.domain.shared.enums import IncidentStatus
from raahat.infrastructure.database.models.incident import IncidentModel
from raahat.infrastructure.database.models.operation import (
    AssignmentModel,
    DispatchDecisionModel,
    OperationEventModel,
)
from raahat.infrastructure.database.models.resource import ResourceModel
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.infrastructure.providers.base import ProviderError

logger = logging.getLogger(__name__)

# Field milestones in order. A later milestone may be reported without the
# earlier ones (field updates are often sparse); going backwards is refused.
STAGES = ("approved", "acknowledged", "en_route", "on_scene", "rescued", "closed")
ACTIVE_RESPONSE_STAGES = frozenset({"en_route", "on_scene"})
COMPLETING_STAGES = frozenset({"rescued", "closed"})
MAX_ROUTED_CANDIDATES = 5


class DispatchError(ValueError):
    """A dispatch command was refused for a reason the operator can act on."""


class DispatchConflict(DispatchError):
    """The resource or incident changed underneath the request."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


_INCIDENT_NEED = """
    SELECT i.id, i.reference, i.operational_priority, i.category, i.severity_facts, i.created_at,
           i.status, i.location_status, i.location_uncertainty_m, i.disaster_id,
           ST_Y(i.location::geometry) AS lat, ST_X(i.location::geometry) AS lon
    FROM incidents i
"""
_RESOURCE_STATE = """
    SELECT r.id, r.callsign, r.name, r.resource_type, r.capabilities, r.availability_status,
           r.capacity, r.position_updated_at, r.position_source, r.is_retired,
           ST_Y(r.location::geometry) AS lat, ST_X(r.location::geometry) AS lon
    FROM resources r
    WHERE r.disaster_id = :disaster_id AND r.is_retired = FALSE
"""


def _need(row: Any) -> recommender.IncidentNeed:
    return recommender.IncidentNeed(
        id=row.id,
        reference=row.reference,
        priority=row.operational_priority,
        category=row.category,
        facts=dict(row.severity_facts or {}),
        created_at=row.created_at,
        position=(float(row.lat), float(row.lon)) if row.lat is not None else None,
        location_status=row.location_status,
        location_uncertainty_m=row.location_uncertainty_m,
    )


def _resource_states(session: Session, disaster_id: uuid.UUID) -> list[recommender.ResourceState]:
    rows = session.execute(text(_RESOURCE_STATE), {"disaster_id": disaster_id}).all()
    return [
        recommender.ResourceState(
            id=r.id,
            callsign=r.callsign,
            name=r.name,
            resource_type=r.resource_type,
            capabilities=tuple(effective_capabilities(r.resource_type, r.capabilities or [])),
            status=r.availability_status,
            capacity=r.capacity,
            position=(float(r.lat), float(r.lon)) if r.lat is not None else None,
            position_updated_at=r.position_updated_at,
            position_source=r.position_source,
            is_retired=r.is_retired,
        )
        for r in rows
    ]


def recommendation_to_dict(result: recommender.Recommendation) -> dict[str, Any]:
    data = asdict(result)
    data["incident_id"] = str(result.incident_id)
    data["generated_at"] = result.generated_at.isoformat()
    for group in ("candidates", "excluded"):
        for item in data[group]:
            item["resource_id"] = str(item["resource_id"])
    return data


def recommend_for_incident(
    session: Session, incident_id: uuid.UUID, *, providers: Optional[Providers] = None
) -> tuple[recommender.Recommendation, PriorityScore, str]:
    """Compute a recommendation. Read-only: nothing is stored."""
    row = session.execute(text(f"{_INCIDENT_NEED} WHERE i.id = :id"), {"id": incident_id}).first()
    if row is None:
        raise LookupError("Incident not found")
    need = _need(row)
    resources = _resource_states(session, row.disaster_id)
    now = _now()
    result = recommender.recommend(need, resources, now=now)

    # Where a routing service is configured, replace straight-line distance with
    # road distance for the leading candidates and rank again.
    routing = providers.routing if providers else None
    if routing is not None and routing.configured and need.position is not None:
        by_id = {r.id: r for r in resources}
        routes: dict[uuid.UUID, recommender.RouteInfo] = {}
        for candidate in result.candidates[:MAX_ROUTED_CANDIDATES]:
            state = by_id[candidate.resource_id]
            if state.position is None:
                continue
            try:
                estimate = routing.route(origin=state.position, destination=need.position)
            except ProviderError as exc:
                logger.warning("Routing failed for %s: %s", state.callsign, exc)
                continue
            routes[state.id] = recommender.RouteInfo(
                estimate.distance_m, estimate.duration_s, estimate.provider
            )
        if routes:
            result = recommender.recommend(need, resources, now=now, routes=routes)

    score = score_incident(
        priority=need.priority, facts=need.facts, created_at=need.created_at, now=now
    )
    return result, score, row.status


def priority_queue(session: Session, disaster_id: uuid.UUID, *, limit: int = 100) -> list[dict[str, Any]]:
    """Incidents awaiting a resource, ordered by priority score."""
    rows = session.execute(
        text(
            f"{_INCIDENT_NEED} WHERE i.disaster_id = :disaster_id AND i.status = 'verified' "
            "AND NOT EXISTS (SELECT 1 FROM assignments a WHERE a.incident_id = i.id "
            "AND a.status = 'approved') LIMIT 500"
        ),
        {"disaster_id": disaster_id},
    ).all()
    now = _now()
    scored = []
    for row in rows:
        need = _need(row)
        score = score_incident(
            priority=need.priority, facts=need.facts, created_at=need.created_at, now=now
        )
        scored.append((need, score))
    scored.sort(key=lambda pair: (-pair[1].total, pair[0].created_at))
    return [
        {"need": need, "score": score} for need, score in scored[:limit]
    ]


def build_plan(session: Session, disaster_id: uuid.UUID) -> list[recommender.PlanEntry]:
    queue = priority_queue(session, disaster_id)
    resources = _resource_states(session, disaster_id)
    return recommender.plan([(q["need"], q["score"].total) for q in queue], resources, now=_now())


# ------------------------------------------------------------------ decisions
def approve_assignment(
    session: Session,
    *,
    incident_id: uuid.UUID,
    resource_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: Optional[str],
    providers: Optional[Providers] = None,
) -> tuple[AssignmentModel, DispatchDecisionModel]:
    """A person commits a resource to an incident.

    The engine's recommendation is recomputed inside this transaction and
    stored with the decision. Choosing anything other than its first-ranked
    resource is an override and requires a reason.
    """
    incident = session.get(IncidentModel, incident_id, with_for_update=True)
    if incident is None:
        raise LookupError("Incident not found")
    if IncidentStatus(incident.status) not in DISPATCHABLE_STATUSES:
        raise DispatchError(
            f"This incident is '{incident.status}'. A person must verify an incident "
            "before resources are committed to it."
        )
    resource = session.get(ResourceModel, resource_id, with_for_update=True)
    if resource is None:
        raise LookupError("Resource not found")
    if resource.disaster_id != incident.disaster_id:
        raise DispatchError("The resource belongs to a different operation")
    if resource.is_retired or resource.availability_status != "available":
        raise DispatchConflict(
            f"{resource.callsign} is no longer available (status: {resource.availability_status})"
        )

    result, _, _ = recommend_for_incident(session, incident_id, providers=providers)
    best = result.best
    followed = best is not None and best.resource_id == resource_id
    chosen = next((c for c in result.candidates if c.resource_id == resource_id), None)
    if not followed and not (reason and reason.strip()):
        raise DispatchError(
            "This is not the resource the system ranked first. "
            "Give a reason for choosing it."
        )

    now = _now()
    decision = DispatchDecisionModel(
        id=uuid.uuid4(),
        incident_id=incident_id,
        decision="approved",
        chosen_resource_id=resource_id,
        recommended_resource_id=best.resource_id if best else None,
        followed_recommendation=followed,
        recommendation=recommendation_to_dict(result),
        reason=(reason or "").strip() or None,
        decided_by=actor_id,
    )
    assignment = AssignmentModel(
        id=uuid.uuid4(),
        incident_id=incident_id,
        resource_id=resource_id,
        assigned_by=actor_id,
        status="approved",
        stage="approved",
        notes=(reason or "").strip() or None,
        decision_id=decision.id,
        approved_at=now,
    )
    decision.assignment_id = assignment.id
    session.add_all([decision, assignment])
    resource.availability_status = "assigned"
    resource.updated_at = now
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DispatchConflict(
            f"{resource.callsign} was committed to another incident a moment ago"
        ) from exc
    session.add(
        OperationEventModel(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            incident_id=incident_id,
            event_type="approved",
            actor_id=actor_id,
            notes=(reason or "").strip() or None,
            payload={"resource_id": str(resource_id)},
        )
    )
    previous_status = incident.status
    if incident.status == IncidentStatus.VERIFIED.value:
        incident.status = IncidentStatus.ASSIGNED.value
    incident.updated_at = now
    session.flush()

    append_audit(
        session,
        action="dispatch.approved",
        actor_id=actor_id,
        entity_type="assignment",
        entity_id=assignment.id,
        disaster_id=incident.disaster_id,
        incident_id=incident_id,
        payload={
            "incident_reference": incident.reference,
            "resource_id": str(resource_id),
            "callsign": resource.callsign,
            "followed_recommendation": followed,
            "recommended_callsign": best.callsign if best else None,
            "chosen_score": chosen.score if chosen else None,
            "recommended_score": best.score if best else None,
            "reason": decision.reason,
            "decision_id": str(decision.id),
        },
    )
    if previous_status != incident.status:
        append_audit(
            session,
            action="incident.status_changed",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident_id,
            disaster_id=incident.disaster_id,
            payload={"from": previous_status, "to": incident.status, "cause": "dispatch.approved"},
        )
    return assignment, decision


def reject_recommendation(
    session: Session, *, incident_id: uuid.UUID, actor_id: uuid.UUID, reason: str,
    providers: Optional[Providers] = None,
) -> DispatchDecisionModel:
    """Record that a person declined to commit any resource right now, and why."""
    incident = session.get(IncidentModel, incident_id)
    if incident is None:
        raise LookupError("Incident not found")
    if not reason.strip():
        raise DispatchError("A reason is required")
    result, _, _ = recommend_for_incident(session, incident_id, providers=providers)
    best = result.best
    decision = DispatchDecisionModel(
        id=uuid.uuid4(),
        incident_id=incident_id,
        decision="rejected",
        chosen_resource_id=None,
        recommended_resource_id=best.resource_id if best else None,
        followed_recommendation=False if best else None,
        recommendation=recommendation_to_dict(result),
        reason=reason.strip(),
        decided_by=actor_id,
    )
    session.add(decision)
    session.flush()
    append_audit(
        session,
        action="dispatch.recommendation_rejected",
        actor_id=actor_id,
        entity_type="incident",
        entity_id=incident_id,
        disaster_id=incident.disaster_id,
        payload={
            "recommended_callsign": best.callsign if best else None,
            "reason": reason.strip(),
            "decision_id": str(decision.id),
        },
    )
    return decision


def _other_active_assignments(session: Session, incident_id: uuid.UUID, exclude: uuid.UUID) -> list[AssignmentModel]:
    return list(
        session.execute(
            select(AssignmentModel).where(
                AssignmentModel.incident_id == incident_id,
                AssignmentModel.status == "approved",
                AssignmentModel.id != exclude,
            )
        ).scalars()
    )


def record_progress(
    session: Session,
    *,
    assignment_id: uuid.UUID,
    stage: str,
    actor_id: uuid.UUID,
    note: Optional[str] = None,
) -> AssignmentModel:
    """Record a field milestone or cancel an assignment."""
    assignment = session.get(AssignmentModel, assignment_id, with_for_update=True)
    if assignment is None:
        raise LookupError("Assignment not found")
    if assignment.status != "approved":
        raise DispatchError(f"This assignment is already {assignment.status}")
    cancelling = stage == "cancelled"
    if not cancelling:
        if stage not in STAGES or stage == "approved":
            raise DispatchError(
                "Stage must be one of: acknowledged, en_route, on_scene, rescued, closed, cancelled"
            )
        if STAGES.index(stage) <= STAGES.index(assignment.stage):
            raise DispatchError(
                f"The assignment is already at '{assignment.stage}'; it cannot move to '{stage}'"
            )
    elif not (note and note.strip()):
        raise DispatchError("Cancelling an assignment requires a note")

    incident = session.get(IncidentModel, assignment.incident_id, with_for_update=True)
    resource = session.get(ResourceModel, assignment.resource_id, with_for_update=True)
    assert incident is not None and resource is not None
    now = _now()
    previous_stage = assignment.stage
    previous_incident_status = incident.status
    assignment.stage = stage
    assignment.updated_at = now

    finishing = cancelling or stage in COMPLETING_STAGES
    if finishing:
        assignment.status = "cancelled" if cancelling else "completed"
        assignment.completed_at = now
        resource.availability_status = "available"
        resource.updated_at = now
        others = _other_active_assignments(session, incident.id, assignment.id)
        if not others and incident.status in (
            IncidentStatus.ASSIGNED.value, IncidentStatus.IN_PROGRESS.value,
        ):
            if cancelling and incident.status == IncidentStatus.ASSIGNED.value:
                # Nothing is committed any more: back to awaiting dispatch.
                incident.status = IncidentStatus.VERIFIED.value
            elif not cancelling and incident.status == IncidentStatus.ASSIGNED.value:
                # Completed without en-route/on-scene being reported.
                incident.status = IncidentStatus.IN_PROGRESS.value
    elif stage in ACTIVE_RESPONSE_STAGES and incident.status == IncidentStatus.ASSIGNED.value:
        incident.status = IncidentStatus.IN_PROGRESS.value
    incident.updated_at = now

    session.add(
        OperationEventModel(
            id=uuid.uuid4(),
            assignment_id=assignment.id,
            incident_id=incident.id,
            event_type=stage,
            actor_id=actor_id,
            notes=(note or "").strip() or None,
            payload={"from": previous_stage},
        )
    )
    session.flush()
    append_audit(
        session,
        action=f"dispatch.{stage}",
        actor_id=actor_id,
        entity_type="assignment",
        entity_id=assignment.id,
        disaster_id=incident.disaster_id,
        incident_id=incident.id,
        payload={
            "incident_reference": incident.reference,
            "callsign": resource.callsign,
            "from": previous_stage,
            "to": stage,
            "note": note,
            "resource_released": finishing,
        },
    )
    if previous_incident_status != incident.status:
        append_audit(
            session,
            action="incident.status_changed",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident.id,
            disaster_id=incident.disaster_id,
            payload={
                "from": previous_incident_status,
                "to": incident.status,
                "cause": f"dispatch.{stage}",
            },
        )
    return assignment


_ASSIGNMENTS = """
    SELECT a.id, a.incident_id, a.resource_id, a.status, a.stage, a.notes, a.assigned_by,
           a.approved_at, a.completed_at, a.created_at, a.updated_at, a.decision_id,
           i.reference AS incident_reference, i.operational_priority, i.status AS incident_status,
           i.location_label, i.category,
           r.callsign, r.name AS resource_name, r.resource_type,
           d.followed_recommendation, d.reason AS decision_reason
    FROM assignments a
    JOIN incidents i ON i.id = a.incident_id
    JOIN resources r ON r.id = a.resource_id
    LEFT JOIN dispatch_decisions d ON d.id = a.decision_id
"""


def list_assignments(
    session: Session,
    *,
    disaster_id: Optional[uuid.UUID] = None,
    incident_id: Optional[uuid.UUID] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["TRUE"]
    params: dict[str, Any] = {}
    if disaster_id is not None:
        clauses.append("i.disaster_id = :disaster_id")
        params["disaster_id"] = disaster_id
    if incident_id is not None:
        clauses.append("a.incident_id = :incident_id")
        params["incident_id"] = incident_id
    if active_only:
        clauses.append("a.status = 'approved'")
    where = " WHERE " + " AND ".join(clauses)
    total = session.execute(
        text(f"SELECT count(*) FROM assignments a JOIN incidents i ON i.id = a.incident_id{where}"),
        params,
    ).scalar_one()
    rows = session.execute(
        text(
            f"{_ASSIGNMENTS}{where} ORDER BY (a.status = 'approved') DESC, a.created_at DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows], total
