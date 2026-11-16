"""Incidents: queue, detail, lifecycle, corrections, location evidence, duplicate review, timeline."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.deps import CurrentUser, get_db, get_session_factory, require
from raahat.api.schemas import Coordinates, Page, Pagination, coordinates_or_none, split_csv
from raahat.api.services import get_incident_commands, get_pipeline, providers
from raahat.application.incident_resolution import IncidentReviewService, LinkReviewAction
from raahat.application.incidents import service as incidents
from raahat.application.incidents.service import IncidentCommands, IncidentError, IncidentQuery
from raahat.application.intake.pipeline import ReportPipeline
from raahat.application.location import service as locations
from raahat.application.system.status import record_integration_result
from raahat.domain.incidents.lifecycle import (
    ALLOWED_TRANSITIONS,
    CLOSURE_REASONS,
    OPERATOR_SETTABLE,
    InvalidTransitionError,
)
from raahat.domain.shared.enums import (
    IncidentCategory,
    IncidentStatus,
    LocationSource,
    PriorityLevel,
)
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.incident import IncidentLinkModel, IncidentModel
from raahat.infrastructure.database.models.user import UserModel
from raahat.infrastructure.providers.base import ProviderError, ProviderNotConfigured
from raahat.security.permissions import Permission

router = APIRouter(prefix="/incidents", tags=["incidents"])


# ------------------------------------------------------------------- schemas
class IncidentLocation(BaseModel):
    status: str  # none | candidate | confirmed
    coordinates: Optional[Coordinates]
    source: Optional[str]
    label: Optional[str]
    description: Optional[str]
    # Ranking score of the chosen candidate (name similarity or provider
    # importance). Not a probability.
    score: Optional[float]
    uncertainty_radius_m: Optional[float]


class IncidentSummary(BaseModel):
    id: uuid.UUID
    reference: str
    disaster_id: uuid.UUID
    status: str
    category: str
    summary: Optional[str]
    priority: str
    priority_source: str
    priority_reasons: list[str]
    people_count: Optional[int]
    trapped: Optional[bool]
    medical_emergency: Optional[bool]
    needs: list[str]
    hazards: list[str]
    source_channel: Optional[str]
    location: IncidentLocation
    report_count: int
    active_assignments: int
    pending_duplicates: int
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime]
    merged_into_id: Optional[uuid.UUID]


class FactSource(BaseModel):
    report_id: uuid.UUID
    value: Any
    extractor: str
    model: Optional[str]
    quote: Optional[str]
    note: Optional[str]
    confidence: Optional[float]


class Fact(BaseModel):
    name: str
    value: Any
    known: bool
    origin: str  # operator | extracted | unknown
    set_by: Optional[str]
    set_at: Optional[str]
    sources: list[FactSource]


class LocationCandidate(BaseModel):
    id: uuid.UUID
    coordinates: Coordinates
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
    is_current: bool


class DuplicateSignal(BaseModel):
    name: str
    weight: float
    score: float
    detail: str


class DuplicateCandidate(BaseModel):
    link_id: uuid.UUID
    status: str
    link_type: str
    score: Optional[float]
    signals: list[DuplicateSignal]
    other: IncidentSummary
    created_at: datetime
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    review_reason: Optional[str]
    merge_event_id: Optional[uuid.UUID] = None


class IncidentDetail(IncidentSummary):
    facts: list[Fact]
    unknown_fields: list[str]
    triage: dict[str, Any]
    location_candidates: list[LocationCandidate]
    duplicates: list[DuplicateCandidate]
    allowed_statuses: list[str]
    closure_reason: Optional[str]
    closed_at: Optional[datetime]
    resolved_at: Optional[datetime]
    verified_by: Optional[uuid.UUID]


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus
    note: Optional[str] = Field(default=None, max_length=1000)
    closure_reason: Optional[str] = None


class CorrectionRequest(BaseModel):
    """Operator corrections. Omitted fields are left alone; a fact set to null becomes unknown."""

    model_config = ConfigDict(extra="forbid")

    facts: Optional[dict[str, Any]] = None
    category: Optional[IncidentCategory] = None
    summary: Optional[str] = Field(default=None, max_length=500)
    location_description: Optional[str] = Field(default=None, max_length=512)
    priority: Optional[PriorityLevel] = None
    clear_priority_override: bool = False
    note: Optional[str] = Field(default=None, max_length=1000)


class SetLocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    label: Optional[str] = Field(default=None, max_length=255)
    uncertainty_radius_m: Optional[float] = Field(default=None, ge=0, le=100_000)
    note: Optional[str] = Field(default=None, max_length=500)


class CandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=500)


class LandmarkSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phrase: str = Field(min_length=3, max_length=120)


class GeocodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=3, max_length=200)


class DuplicateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # merge: this incident is a duplicate of the other, fold it in
    # reject: they are different incidents
    # relate: different incidents that belong to one situation
    action: str = Field(pattern="^(merge|reject|relate)$")
    reason: str = Field(min_length=3, max_length=500)
    keep: Optional[uuid.UUID] = Field(
        default=None, description="For merge: the incident that survives. Defaults to the other one."
    )


class UnmergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class TimelineEntry(BaseModel):
    seq: int
    action: str
    entity_type: str
    entity_id: uuid.UUID
    actor_id: Optional[uuid.UUID]
    actor_name: Optional[str]
    occurred_at: datetime
    payload: dict[str, Any]


class IncidentCounts(BaseModel):
    by_status: dict[str, int]
    open_by_priority: dict[str, int]
    open_without_location: int
    generated_at: datetime


# ------------------------------------------------------------------- helpers
def _summary(row: dict[str, Any]) -> IncidentSummary:
    facts = row["severity_facts"] or {}
    triage = row["triage"] or {}
    people = facts.get("people_count")
    return IncidentSummary(
        id=row["id"], reference=row["reference"], disaster_id=row["disaster_id"],
        status=row["status"], category=row["category"], summary=row["summary"],
        priority=row["operational_priority"],
        priority_source=triage.get("source", "none"),
        priority_reasons=list(triage.get("reasons") or []),
        people_count=people if isinstance(people, int) else None,
        trapped=facts.get("trapped_status"), medical_emergency=facts.get("medical_emergency"),
        needs=list(facts.get("relief_needs") or []), hazards=list(facts.get("hazards") or []),
        source_channel=row["source_channel"],
        location=IncidentLocation(
            status=row["location_status"],
            coordinates=coordinates_or_none(row["latitude"], row["longitude"]),
            source=row["location_source"], label=row["location_label"],
            description=row["location_description"], score=row["location_confidence"],
            uncertainty_radius_m=row["location_uncertainty_m"],
        ),
        report_count=row["report_count"], active_assignments=row["active_assignments"],
        pending_duplicates=row["pending_duplicates"], created_at=row["created_at"],
        updated_at=row["updated_at"], verified_at=row["verified_at"],
        merged_into_id=row["merged_into_id"],
    )


def _resolve(session: Session, identifier: str) -> uuid.UUID:
    incident_id = incidents.resolve_incident_id(session, identifier)
    if incident_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return incident_id


def _duplicates(session: Session, incident_id: uuid.UUID) -> list[DuplicateCandidate]:
    links = session.execute(
        select(IncidentLinkModel)
        .where((IncidentLinkModel.incident_a_id == incident_id) | (IncidentLinkModel.incident_b_id == incident_id))
        .order_by(IncidentLinkModel.created_at.desc())
    ).scalars().all()
    out: list[DuplicateCandidate] = []
    for link in links:
        other_id = link.incident_b_id if link.incident_a_id == incident_id else link.incident_a_id
        other = incidents.get_incident_row(session, other_id)
        if other is None:
            continue
        merge_event = session.execute(
            text(
                "SELECT id FROM entity_merge_events WHERE status = 'active' AND "
                "((source_entity_id = :a AND target_entity_id = :b) OR "
                "(source_entity_id = :b AND target_entity_id = :a)) LIMIT 1"
            ),
            {"a": incident_id, "b": other_id},
        ).scalar_one_or_none()
        out.append(
            DuplicateCandidate(
                link_id=link.id, status=link.status, link_type=link.link_type,
                score=link.confidence,
                signals=[
                    DuplicateSignal(
                        name=str(s.get("name", "")), weight=float(s.get("weight", 0)),
                        score=float(s.get("score", 0)), detail=str(s.get("detail", "")),
                    )
                    for s in (link.signals or [])
                ],
                other=_summary(other), created_at=link.created_at, reviewed_by=link.reviewed_by,
                reviewed_at=link.reviewed_at, review_reason=link.review_reason,
                merge_event_id=merge_event,
            )
        )
    return out


def _detail(session: Session, incident_id: uuid.UUID) -> IncidentDetail:
    row = incidents.get_incident_row(session, incident_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    incident = session.get(IncidentModel, incident_id)
    assert incident is not None
    summary = _summary(row)
    current = IncidentStatus(incident.status)
    candidates = [
        LocationCandidate(
            id=h.id, coordinates=Coordinates(latitude=h.latitude, longitude=h.longitude),
            label=h.label, source=h.source, source_detail=h.source_detail, score=h.score,
            uncertainty_radius_m=h.uncertainty_radius_m, verification_status=h.verification_status,
            report_id=h.report_id, confirmed_by=h.confirmed_by, confirmed_at=h.confirmed_at,
            created_at=h.created_at, is_current=h.id == incident.location_hypothesis_id,
        )
        for h in locations.list_hypotheses(session, incident_id)
    ]
    return IncidentDetail(
        **summary.model_dump(),
        facts=[Fact(**f) for f in incidents.fact_sheet(session, incident)],
        unknown_fields=list((incident.triage or {}).get("unknown_fields") or []),
        triage=dict(incident.triage or {}),
        location_candidates=candidates,
        duplicates=_duplicates(session, incident_id),
        allowed_statuses=sorted(s.value for s in ALLOWED_TRANSITIONS[current] & OPERATOR_SETTABLE),
        closure_reason=incident.closure_reason, closed_at=incident.closed_at,
        resolved_at=incident.resolved_at, verified_by=incident.verified_by,
    )


# -------------------------------------------------------------------- reads
@router.get("", response_model=Page[IncidentSummary], summary="List incidents")
def list_incidents(
    disaster_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Comma-separated statuses, or 'open'"
    ),
    priority: Optional[str] = Query(None, description="Comma-separated priority levels"),
    category: Optional[str] = Query(None, description="Comma-separated categories"),
    q: Optional[str] = Query(None, max_length=200),
    location_status: Optional[str] = Query(None, pattern="^(none|candidate|confirmed)$"),
    needs_review: Optional[bool] = Query(None),
    bbox: Optional[str] = Query(None, description="west,south,east,north"),
    sort: str = Query("priority", pattern="^(priority|newest|oldest|updated|reference)$"),
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> Page[IncidentSummary]:
    statuses = split_csv(status_filter)
    if "open" in statuses:
        statuses = ["unverified", "under_review", "verified", "assigned", "in_progress"]
    valid = {s.value for s in IncidentStatus}
    if any(s not in valid for s in statuses):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status in filter")
    box: Optional[tuple[float, float, float, float]] = None
    if bbox:
        try:
            west, south, east, north = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bbox must be west,south,east,north") from None
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bbox is out of range")
        box = (west, south, east, north)
    rows, total = incidents.list_incidents(
        session,
        IncidentQuery(
            disaster_id=disaster_id, statuses=statuses, priorities=split_csv(priority),
            categories=split_csv(category), search=q, location_status=location_status,
            needs_review=needs_review, bbox=box, sort=sort, limit=page.limit, offset=page.offset,
        ),
    )
    return Page(items=[_summary(r) for r in rows], total=total, limit=page.limit, offset=page.offset)


@router.get("/counts", response_model=IncidentCounts, summary="Incident counts by status and priority")
def incident_counts(
    disaster_id: Optional[uuid.UUID] = Query(None),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> IncidentCounts:
    return IncidentCounts(**incidents.status_counts(session, disaster_id))


@router.get("/{incident}", response_model=IncidentDetail, summary="Get an incident by id or reference")
def get_incident(
    incident: str,
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    return _detail(session, _resolve(session, incident))


@router.get("/{incident}/timeline", response_model=Page[TimelineEntry], summary="Everything that happened to an incident")
def incident_timeline(
    incident: str,
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> Page[TimelineEntry]:
    incident_id = _resolve(session, incident)
    total = session.execute(
        text("SELECT count(*) FROM audit_events WHERE incident_id = :id"), {"id": incident_id}
    ).scalar_one()
    rows = session.execute(
        select(AuditEventModel, UserModel.full_name)
        .outerjoin(UserModel, UserModel.id == AuditEventModel.actor_id)
        .where(AuditEventModel.incident_id == incident_id)
        .order_by(AuditEventModel.seq.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page(
        items=[
            TimelineEntry(
                seq=e.seq, action=e.action, entity_type=e.entity_type, entity_id=e.entity_id,
                actor_id=e.actor_id, actor_name=name, occurred_at=e.created_at, payload=e.payload or {},
            )
            for e, name in rows
        ],
        total=total, limit=page.limit, offset=page.offset,
    )


# ----------------------------------------------------------------- commands
@router.post("/{incident}/status", response_model=IncidentDetail, summary="Change an incident's status")
def change_status(
    incident: str,
    body: StatusRequest,
    actor: CurrentUser = Depends(require(Permission.INCIDENTS_UPDATE)),
    session: Session = Depends(get_db),
    commands: IncidentCommands = Depends(get_incident_commands),
) -> IncidentDetail:
    """Move an incident through its lifecycle. Verifying requires the verify permission."""
    incident_id = _resolve(session, incident)
    if body.status == IncidentStatus.VERIFIED and not actor.can(Permission.INCIDENTS_VERIFY):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit verifying incidents")
    if body.closure_reason is not None and body.closure_reason not in CLOSURE_REASONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown closure reason")
    try:
        commands.change_status(
            session, incident_id=incident_id, target=body.status, actor_id=actor.id,
            note=body.note, closure_reason=body.closure_reason,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except (InvalidTransitionError, IncidentError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    session.commit()
    return _detail(session, incident_id)


@router.patch("/{incident}", response_model=IncidentDetail, summary="Correct incident details")
def correct_incident(
    incident: str,
    body: CorrectionRequest,
    actor: CurrentUser = Depends(require(Permission.INCIDENTS_UPDATE)),
    session: Session = Depends(get_db),
    commands: IncidentCommands = Depends(get_incident_commands),
) -> IncidentDetail:
    incident_id = _resolve(session, incident)
    try:
        commands.correct(
            session, incident_id=incident_id, actor_id=actor.id, facts=body.facts,
            category=body.category, summary=body.summary,
            location_description=body.location_description, priority=body.priority,
            clear_priority_override=body.clear_priority_override, note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except IncidentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    session.commit()
    return _detail(session, incident_id)


# ----------------------------------------------------------------- location
@router.put("/{incident}/location", response_model=IncidentDetail, summary="Set the incident position")
def set_location(
    incident: str,
    body: SetLocationRequest,
    actor: CurrentUser = Depends(require(Permission.LOCATIONS_CONFIRM)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    """Record a position entered or placed on the map by the operator. It becomes the confirmed position."""
    incident_id = _resolve(session, incident)
    try:
        locations.set_operator_location(
            session, incident_id=incident_id, latitude=body.latitude, longitude=body.longitude,
            actor_id=actor.id, label=body.label, uncertainty_radius_m=body.uncertainty_radius_m,
            note=body.note,
        )
    except locations.LocationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    session.commit()
    return _detail(session, incident_id)


@router.post("/{incident}/location-candidates/{candidate_id}/confirm", response_model=IncidentDetail,
             summary="Confirm a location candidate")
def confirm_candidate(
    incident: str,
    candidate_id: uuid.UUID,
    body: CandidateDecision,
    actor: CurrentUser = Depends(require(Permission.LOCATIONS_CONFIRM)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    incident_id = _resolve(session, incident)
    try:
        locations.confirm_hypothesis(
            session, incident_id=incident_id, hypothesis_id=candidate_id, actor_id=actor.id, note=body.note
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    session.commit()
    return _detail(session, incident_id)


@router.post("/{incident}/location-candidates/{candidate_id}/reject", response_model=IncidentDetail,
             summary="Reject a location candidate")
def reject_candidate(
    incident: str,
    candidate_id: uuid.UUID,
    body: CandidateDecision,
    actor: CurrentUser = Depends(require(Permission.LOCATIONS_CONFIRM)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    incident_id = _resolve(session, incident)
    try:
        locations.reject_hypothesis(
            session, incident_id=incident_id, hypothesis_id=candidate_id, actor_id=actor.id, reason=body.note
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    session.commit()
    return _detail(session, incident_id)


@router.post("/{incident}/location-candidates/landmarks", response_model=IncidentDetail,
             summary="Search the landmark gazetteer and add matches as candidates")
def add_landmark_candidates(
    incident: str,
    body: LandmarkSearchRequest,
    actor: CurrentUser = Depends(require(Permission.LOCATIONS_CONFIRM)),
    session: Session = Depends(get_db),
    pipeline: ReportPipeline = Depends(get_pipeline),
) -> IncidentDetail:
    incident_id = _resolve(session, incident)
    model = session.get(IncidentModel, incident_id)
    assert model is not None
    report_row = session.execute(
        text("SELECT report_id FROM incident_reports WHERE incident_id = :id ORDER BY created_at LIMIT 1"),
        {"id": incident_id},
    ).first()
    if report_row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Incident has no report")
    from raahat.infrastructure.database.models.report import ReportModel

    report = session.get(ReportModel, report_row.report_id)
    assert report is not None
    pipeline._add_landmark_candidates(
        session, model, report, [(body.phrase.strip(), None)], extractor=f"operator:{actor.username}"
    )
    locations.refresh_incident_location(session, model)
    session.commit()
    return _detail(session, incident_id)


@router.post("/{incident}/location-candidates/geocode", response_model=IncidentDetail,
             summary="Look a place up with the geocoder and add results as candidates")
def geocode_candidates(
    incident: str,
    body: GeocodeRequest,
    actor: CurrentUser = Depends(require(Permission.LOCATIONS_CONFIRM)),
    session: Session = Depends(get_db),
) -> IncidentDetail:
    """Runs one geocoder query at the operator's request. Results are candidates, not positions."""
    incident_id = _resolve(session, incident)
    model = session.get(IncidentModel, incident_id)
    assert model is not None
    geocoder = providers().geocoder
    try:
        result = geocoder.search(body.query, limit=5)
    except ProviderNotConfigured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "No geocoder is configured for this deployment. Set GEOCODER_PROVIDER to enable lookups.",
        ) from None
    except ProviderError as exc:
        record_integration_result(session, "geocoder", ok=False, detail=str(exc))
        session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The geocoder did not respond: {exc}") from None
    record_integration_result(
        session, "geocoder", ok=True, detail=f"{len(result.candidates)} result(s) for a lookup",
        latency_ms=result.duration_ms,
    )
    existing = {
        str(v.source_detail.get("osm_ref"))
        for v in locations.list_hypotheses(session, incident_id)
        if v.source == LocationSource.GEOCODER.value
    }
    for candidate in result.candidates:
        if candidate.osm_ref and candidate.osm_ref in existing:
            continue
        locations.add_hypothesis(
            session, incident_id=incident_id, latitude=candidate.latitude,
            longitude=candidate.longitude, source=LocationSource.GEOCODER,
            label=candidate.label[:255],
            score=min(1.0, max(0.0, candidate.importance)) if candidate.importance is not None else None,
            uncertainty_radius_m=candidate.bounding_radius_m,
            source_detail={
                "provider": result.provider, "query": result.query, "osm_ref": candidate.osm_ref,
                "kind": candidate.kind, "score_basis": "provider importance (ranking only)",
                "requested_by": str(actor.id), "licence": "OpenStreetMap contributors, ODbL",
            },
        )
    locations.refresh_incident_location(session, model)
    session.commit()
    return _detail(session, incident_id)


# --------------------------------------------------------------- duplicates
@router.post("/{incident}/duplicates/{link_id}/review", response_model=IncidentDetail,
             summary="Decide on a possible duplicate")
def review_duplicate(
    incident: str,
    link_id: uuid.UUID,
    body: DuplicateReview,
    actor: CurrentUser = Depends(require(Permission.INCIDENTS_MERGE)),
    session: Session = Depends(get_db),
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> IncidentDetail:
    """Merge, reject or relate two incidents. Original reports are always kept; a merge can be reversed."""
    incident_id = _resolve(session, incident)
    link = session.get(IncidentLinkModel, link_id)
    if link is None or incident_id not in (link.incident_a_id, link.incident_b_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Duplicate candidate not found for this incident")
    other_id = link.incident_b_id if link.incident_a_id == incident_id else link.incident_a_id
    review = IncidentReviewService(factory)
    action = {
        "merge": LinkReviewAction.APPROVE_MERGE,
        "reject": LinkReviewAction.REJECT_MERGE,
        "relate": LinkReviewAction.RELATE_CLUSTER,
    }[body.action]
    source_id, target_id = incident_id, other_id
    if body.action == "merge":
        keep = body.keep or other_id
        if keep not in (incident_id, other_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "'keep' must be one of the two incidents")
        target_id = keep
        source_id = other_id if keep == incident_id else incident_id
    try:
        review.review_link(
            source_incident_id=source_id, target_incident_id=target_id, action=action,
            dispatcher_id=actor.id, reason=body.reason, session=session,
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc).strip("'\"")) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    if body.action == "merge":
        # The surviving incident now carries both sets of evidence.
        get_incident_commands()._triage._triage_with_session(target_id, session, actor_id=actor.id)
    session.commit()
    return _detail(session, incident_id)


@router.post("/{incident}/unmerge", response_model=IncidentDetail, summary="Reverse a merge")
def unmerge(
    incident: str,
    body: UnmergeRequest,
    actor: CurrentUser = Depends(require(Permission.INCIDENTS_MERGE)),
    session: Session = Depends(get_db),
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> IncidentDetail:
    """Restore an incident that was merged into another. Call on the duplicate."""
    incident_id = _resolve(session, incident)
    model = session.get(IncidentModel, incident_id)
    if model is None or model.status != IncidentStatus.DUPLICATE.value or model.merged_into_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This incident is not merged into another")
    target_id = model.merged_into_id
    try:
        IncidentReviewService(factory).review_link(
            source_incident_id=incident_id, target_incident_id=target_id,
            action=LinkReviewAction.UNMERGE, dispatcher_id=actor.id, reason=body.reason, session=session,
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc).strip("'\"")) from None
    commands = get_incident_commands()
    commands._triage._triage_with_session(target_id, session, actor_id=actor.id)
    commands._triage._triage_with_session(incident_id, session, actor_id=actor.id)
    session.commit()
    return _detail(session, incident_id)


@router.get("/duplicates/pending", response_model=Page[DuplicateCandidate],
            summary="Possible duplicates awaiting review", include_in_schema=True)
def pending_duplicates(
    disaster_id: Optional[uuid.UUID] = Query(None),
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
) -> Page[DuplicateCandidate]:
    scope = " AND i.disaster_id = :disaster_id" if disaster_id else ""
    params: dict[str, Any] = {"disaster_id": disaster_id} if disaster_id else {}
    total = session.execute(
        text(
            "SELECT count(*) FROM incident_links l JOIN incidents i ON i.id = l.incident_a_id "
            f"WHERE l.status = 'pending_review'{scope}"
        ),
        params,
    ).scalar_one()
    rows = session.execute(
        text(
            "SELECT l.id, l.incident_a_id FROM incident_links l JOIN incidents i ON i.id = l.incident_a_id "
            f"WHERE l.status = 'pending_review'{scope} ORDER BY l.confidence DESC NULLS LAST, l.created_at "
            "LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page.limit, "offset": page.offset},
    ).all()
    items: list[DuplicateCandidate] = []
    for row in rows:
        items.extend(d for d in _duplicates(session, row.incident_a_id) if d.link_id == row.id)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)
