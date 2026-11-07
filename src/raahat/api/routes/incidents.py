"""Incident verification, review linking, and unmerge API routes."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from raahat.api.dependencies import (
    get_incident_review_service,
    get_session_factory,
    require_dispatcher_id,
)
from raahat.application.incident_resolution import (
    IncidentDetail,
    IncidentReviewService,
    IncidentVerificationResult,
    LinkReviewAction,
    MergeActionResult,
)
from raahat.domain.incidents.incident import Incident, IncidentLink
from raahat.domain.shared.enums import IncidentStatus, PriorityLevel
from raahat.infrastructure.database.models.incident import IncidentModel

router = APIRouter(prefix="/incidents", tags=["incidents"])


class VerifyIncidentRequest(BaseModel):
    """Payload to confirm or adjust an incident's status and priority."""

    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus = IncidentStatus.VERIFIED
    notes: Optional[str] = None
    operational_priority: Optional[PriorityLevel] = None


class ReviewIncidentLinkRequest(BaseModel):
    """Payload for dispatcher merge approval, rejection, cluster linking, or unmerging."""

    model_config = ConfigDict(extra="forbid")

    target_incident_id: uuid.UUID
    action: LinkReviewAction = LinkReviewAction.APPROVE_MERGE
    reason: str = Field(..., min_length=3, description="Dispatcher justification for decision")
    merge_event_id: Optional[uuid.UUID] = Field(default=None, description="Specific merge event ID for unmerge")


class UnmergeRequest(BaseModel):
    """Convenience payload for dispatcher unmerging two previously merged incidents."""

    model_config = ConfigDict(extra="forbid")

    target_incident_id: uuid.UUID
    reason: str = Field(..., min_length=3, description="Justification for reversing merge")
    merge_event_id: Optional[uuid.UUID] = None


@router.post(
    "/{incident_id}/verify",
    response_model=IncidentVerificationResult,
    status_code=status.HTTP_200_OK,
    summary="Dispatcher human verification of an incident",
)
def verify_incident(
    incident_id: uuid.UUID,
    payload: VerifyIncidentRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: IncidentReviewService = Depends(get_incident_review_service),
) -> IncidentVerificationResult:
    """Verify an incident's operational state with authenticated dispatcher ID and tamper-evident audit logging."""
    try:
        return service.verify_incident(
            incident_id=incident_id,
            dispatcher_id=dispatcher_id,
            status=payload.status,
            notes=payload.notes,
            operational_priority=payload.operational_priority,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/links",
    response_model=MergeActionResult,
    status_code=status.HTTP_200_OK,
    summary="Review candidate incident relationships (merge, reject, cluster, unmerge)",
)
def review_incident_link(
    incident_id: uuid.UUID,
    payload: ReviewIncidentLinkRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: IncidentReviewService = Depends(get_incident_review_service),
) -> MergeActionResult:
    """Execute merge, rejection, cluster relationship, or unmerge between two incidents."""
    try:
        return service.review_link(
            source_incident_id=incident_id,
            target_incident_id=payload.target_incident_id,
            action=payload.action,
            dispatcher_id=dispatcher_id,
            reason=payload.reason,
            merge_event_id=payload.merge_event_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{incident_id}/unmerge",
    response_model=MergeActionResult,
    status_code=status.HTTP_200_OK,
    summary="Reverse an active merge without data loss",
)
def unmerge_incident(
    incident_id: uuid.UUID,
    payload: UnmergeRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: IncidentReviewService = Depends(get_incident_review_service),
) -> MergeActionResult:
    """Reversibly unmerge an incident, restoring original status and report assignments."""
    try:
        return service.review_link(
            source_incident_id=incident_id,
            target_incident_id=payload.target_incident_id,
            action=LinkReviewAction.UNMERGE,
            dispatcher_id=dispatcher_id,
            reason=payload.reason,
            merge_event_id=payload.merge_event_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}",
    response_model=IncidentDetail,
    status_code=status.HTTP_200_OK,
    summary="Get incident detail with linked reports, hypotheses, and links",
)
def get_incident_detail(
    incident_id: uuid.UUID,
    service: IncidentReviewService = Depends(get_incident_review_service),
) -> IncidentDetail:
    """Retrieve full incident aggregate."""
    try:
        return service.get_incident_detail(incident_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{incident_id}/links",
    response_model=list[IncidentLink],
    status_code=status.HTTP_200_OK,
    summary="List all relationship links for an incident",
)
def list_incident_links(
    incident_id: uuid.UUID,
    service: IncidentReviewService = Depends(get_incident_review_service),
) -> list[IncidentLink]:
    """Retrieve candidate links for review queue."""
    try:
        return service.list_incident_links(incident_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[Incident],
    status_code=status.HTTP_200_OK,
    summary="List incidents for a disaster",
)
def list_incidents(
    disaster_id: uuid.UUID = Query(..., description="Disaster ID"),
    status_filter: Optional[IncidentStatus] = Query(None, alias="status"),
    session_factory=Depends(get_session_factory),
) -> list[Incident]:
    """List active incidents for situational awareness and review queues."""
    with session_factory() as session:
        stmt = select(IncidentModel).where(IncidentModel.disaster_id == disaster_id)
        if status_filter:
            stmt = stmt.where(IncidentModel.status == status_filter.value)
        inc_models = session.scalars(stmt).all()

        return [
            Incident(
                id=m.id,
                disaster_id=m.disaster_id,
                status=IncidentStatus(m.status),
                operational_priority=PriorityLevel(m.operational_priority),
                severity_facts=dict(m.severity_facts or {}),
                last_confirmed_at=m.last_confirmed_at,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in inc_models
        ]
