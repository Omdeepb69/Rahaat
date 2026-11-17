"""Dispatch: priority queue, recommendations, human decisions, assignment progress."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from raahat.api import scope as access
from raahat.api.deps import CurrentUser, get_db, require
from raahat.api.schemas import Page, Pagination
from raahat.api.services import providers
from raahat.application.dispatch import recommender
from raahat.application.dispatch import service as dispatch
from raahat.application.dispatch.priority import PriorityScore
from raahat.application.incidents.service import resolve_incident_id
from raahat.security.permissions import Permission

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


class ScoreTerm(BaseModel):
    name: str
    points: float
    detail: str


class PriorityScoreResponse(BaseModel):
    total: float
    terms: list[ScoreTerm]


class RequirementResponse(BaseModel):
    capability: str
    reason: str


class FactorResponse(BaseModel):
    name: str
    weight: float
    value: float
    contribution: float
    detail: str


class CandidateResponse(BaseModel):
    resource_id: uuid.UUID
    callsign: str
    name: str
    resource_type: str
    rank: int
    score: float
    factors: list[FactorResponse]
    covered: list[str]
    missing: list[str]
    distance_m: Optional[float]
    distance_basis: str
    travel_seconds: Optional[float]
    position_age_minutes: Optional[float]
    warnings: list[str]


class ExclusionResponse(BaseModel):
    resource_id: uuid.UUID
    callsign: str
    reason: str


class RecommendationResponse(BaseModel):
    """A ranking for a person to act on. Nothing is committed by requesting it."""

    incident_id: uuid.UUID
    incident_status: str
    can_dispatch: bool
    blocked_reason: Optional[str]
    priority_score: PriorityScoreResponse
    requirements: list[RequirementResponse]
    candidates: list[CandidateResponse]
    excluded: list[ExclusionResponse]
    limitations: list[str]
    objective: str
    engine_version: str
    generated_at: datetime


class QueueEntry(BaseModel):
    incident_id: uuid.UUID
    reference: str
    priority: str
    category: str
    has_position: bool
    created_at: datetime
    priority_score: PriorityScoreResponse


class PlanEntryResponse(BaseModel):
    incident_id: uuid.UUID
    incident_reference: str
    priority_score: float
    candidate: Optional[CandidateResponse]
    reason_unassigned: Optional[str]


class PlanResponse(BaseModel):
    entries: list[PlanEntryResponse]
    method: str
    generated_at: datetime


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: uuid.UUID
    reason: Optional[str] = Field(default=None, max_length=1000)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)


class ProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(pattern="^(acknowledged|en_route|on_scene|rescued|closed|cancelled)$")
    note: Optional[str] = Field(default=None, max_length=1000)


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    incident_reference: str
    incident_status: str
    incident_priority: str
    incident_category: str
    incident_location_label: Optional[str]
    resource_id: uuid.UUID
    callsign: str
    resource_name: str
    resource_type: str
    status: str
    stage: str
    next_stages: list[str]
    notes: Optional[str]
    approved_by: uuid.UUID
    approved_at: Optional[datetime]
    completed_at: Optional[datetime]
    followed_recommendation: Optional[bool]
    decision_reason: Optional[str]
    updated_at: datetime


class DecisionResponse(BaseModel):
    decision_id: uuid.UUID
    decision: str
    followed_recommendation: Optional[bool]
    assignment: Optional[AssignmentResponse]


def _score(score: PriorityScore) -> PriorityScoreResponse:
    return PriorityScoreResponse(
        total=score.total, terms=[ScoreTerm(name=t.name, points=t.points, detail=t.detail) for t in score.terms]
    )


def _candidate(candidate: recommender.Candidate, rank: int) -> CandidateResponse:
    return CandidateResponse(
        resource_id=candidate.resource_id, callsign=candidate.callsign, name=candidate.name,
        resource_type=candidate.resource_type, rank=rank, score=candidate.score,
        factors=[FactorResponse(**f.__dict__) for f in candidate.factors],
        covered=list(candidate.covered), missing=list(candidate.missing),
        distance_m=candidate.distance_m, distance_basis=candidate.distance_basis,
        travel_seconds=candidate.travel_seconds, position_age_minutes=candidate.position_age_minutes,
        warnings=list(candidate.warnings),
    )


def _assignment(row: dict[str, Any]) -> AssignmentResponse:
    next_stages: list[str] = []
    if row["status"] == "approved":
        index = dispatch.STAGES.index(row["stage"]) if row["stage"] in dispatch.STAGES else 0
        next_stages = [*dispatch.STAGES[index + 1 :], "cancelled"]
    return AssignmentResponse(
        id=row["id"], incident_id=row["incident_id"], incident_reference=row["incident_reference"],
        incident_status=row["incident_status"], incident_priority=row["operational_priority"],
        incident_category=row["category"], incident_location_label=row["location_label"],
        resource_id=row["resource_id"], callsign=row["callsign"], resource_name=row["resource_name"],
        resource_type=row["resource_type"], status=row["status"], stage=row["stage"],
        next_stages=next_stages, notes=row["notes"], approved_by=row["assigned_by"],
        approved_at=row["approved_at"], completed_at=row["completed_at"],
        followed_recommendation=row["followed_recommendation"], decision_reason=row["decision_reason"],
        updated_at=row["updated_at"],
    )


def _assignment_by_id(session: Session, assignment_id: uuid.UUID, incident_id: uuid.UUID) -> AssignmentResponse:
    rows, _ = dispatch.list_assignments(session, incident_id=incident_id, limit=200)
    return next(_assignment(r) for r in rows if r["id"] == assignment_id)


def _incident(session: Session, identifier: str) -> uuid.UUID:
    incident_id = resolve_incident_id(session, identifier)
    if incident_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return access.ensure_incident(session, incident_id)


@router.get("/queue", response_model=list[QueueEntry], summary="Verified incidents awaiting a resource, by priority score")
def queue(
    disaster_id: uuid.UUID = Query(...),
    _: CurrentUser = Depends(require(Permission.DISPATCH_READ)),
    session: Session = Depends(get_db),
) -> list[QueueEntry]:
    return [
        QueueEntry(
            incident_id=item["need"].id, reference=item["need"].reference,
            priority=item["need"].priority, category=item["need"].category,
            has_position=item["need"].position is not None, created_at=item["need"].created_at,
            priority_score=_score(item["score"]),
        )
        for item in dispatch.priority_queue(session, access.ensure_operation(session, disaster_id))
    ]


@router.get("/plan", response_model=PlanResponse, summary="Proposed pairing of waiting incidents and available resources")
def plan(
    disaster_id: uuid.UUID = Query(...),
    _: CurrentUser = Depends(require(Permission.DISPATCH_READ)),
    session: Session = Depends(get_db),
) -> PlanResponse:
    """A proposal across all waiting incidents. Each pairing still needs individual approval."""
    entries = dispatch.build_plan(session, access.ensure_operation(session, disaster_id))
    return PlanResponse(
        entries=[
            PlanEntryResponse(
                incident_id=e.incident_id, incident_reference=e.incident_reference,
                priority_score=e.priority_score,
                candidate=_candidate(e.candidate, 1) if e.candidate else None,
                reason_unassigned=e.reason_unassigned,
            )
            for e in entries
        ],
        method=(
            "Highest priority score first; each incident takes its best-scoring available "
            "resource, which is then unavailable to the rest."
        ),
        generated_at=datetime.now().astimezone(),
    )


@router.get("/incidents/{incident}/recommendation", response_model=RecommendationResponse,
            summary="Rank available resources for an incident")
def recommendation(
    incident: str,
    _: CurrentUser = Depends(require(Permission.DISPATCH_READ)),
    session: Session = Depends(get_db),
) -> RecommendationResponse:
    incident_id = _incident(session, incident)
    result, score, incident_status = dispatch.recommend_for_incident(session, incident_id, providers=providers())
    dispatchable = incident_status in ("verified", "assigned", "in_progress")
    return RecommendationResponse(
        incident_id=incident_id, incident_status=incident_status, can_dispatch=dispatchable,
        blocked_reason=None if dispatchable else (
            f"The incident is '{incident_status}'. It must be verified before a resource is committed."
        ),
        priority_score=_score(score),
        requirements=[RequirementResponse(capability=r.capability, reason=r.reason) for r in result.requirements],
        candidates=[_candidate(c, i + 1) for i, c in enumerate(result.candidates)],
        excluded=[ExclusionResponse(**e.__dict__) for e in result.excluded],
        limitations=list(result.limitations), objective=result.objective,
        engine_version=result.engine_version, generated_at=result.generated_at,
    )


@router.post("/incidents/{incident}/approve", response_model=DecisionResponse,
             status_code=status.HTTP_201_CREATED, summary="Commit a resource to an incident")
def approve(
    incident: str,
    body: ApproveRequest,
    actor: CurrentUser = Depends(require(Permission.DISPATCH_DECIDE)),
    session: Session = Depends(get_db),
) -> DecisionResponse:
    """The human decision. Choosing a resource other than the first-ranked one requires a reason."""
    incident_id = _incident(session, incident)
    access.ensure_resource(session, body.resource_id)
    try:
        assignment, decision = dispatch.approve_assignment(
            session, incident_id=incident_id, resource_id=body.resource_id, actor_id=actor.id,
            reason=body.reason, providers=providers(),
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except dispatch.DispatchConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    session.commit()
    return DecisionResponse(
        decision_id=decision.id, decision=decision.decision,
        followed_recommendation=decision.followed_recommendation,
        assignment=_assignment_by_id(session, assignment.id, incident_id),
    )


@router.post("/incidents/{incident}/reject", response_model=DecisionResponse,
             status_code=status.HTTP_201_CREATED, summary="Decline to commit a resource now")
def reject(
    incident: str,
    body: RejectRequest,
    actor: CurrentUser = Depends(require(Permission.DISPATCH_DECIDE)),
    session: Session = Depends(get_db),
) -> DecisionResponse:
    incident_id = _incident(session, incident)
    try:
        decision = dispatch.reject_recommendation(
            session, incident_id=incident_id, actor_id=actor.id, reason=body.reason, providers=providers()
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    session.commit()
    return DecisionResponse(
        decision_id=decision.id, decision=decision.decision,
        followed_recommendation=decision.followed_recommendation, assignment=None,
    )


@router.get("/assignments", response_model=Page[AssignmentResponse], summary="List assignments")
def list_assignments(
    disaster_id: Optional[uuid.UUID] = Query(None),
    incident_id: Optional[uuid.UUID] = Query(None),
    active_only: bool = Query(False),
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.DISPATCH_READ)),
    session: Session = Depends(get_db),
) -> Page[AssignmentResponse]:
    access.list_filter(session, disaster_id, incident_id)
    rows, total = dispatch.list_assignments(
        session, disaster_id=disaster_id, incident_id=incident_id, active_only=active_only,
        limit=page.limit, offset=page.offset,
    )
    return Page(items=[_assignment(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.post("/assignments/{assignment_id}/progress", response_model=AssignmentResponse,
             summary="Record a field milestone or cancel an assignment")
def progress(
    assignment_id: uuid.UUID,
    body: ProgressRequest,
    actor: CurrentUser = Depends(require(Permission.DISPATCH_PROGRESS)),
    session: Session = Depends(get_db),
) -> AssignmentResponse:
    if body.stage == "cancelled" and not actor.can(Permission.DISPATCH_DECIDE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit cancelling assignments")
    access.ensure_assignment(session, assignment_id)
    try:
        assignment = dispatch.record_progress(
            session, assignment_id=assignment_id, stage=body.stage, actor_id=actor.id, note=body.note
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except dispatch.DispatchError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    return _assignment_by_id(session, assignment.id, assignment.incident_id)
