"""Location verification and hypothesis history API routes."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from raahat.api.dependencies import (
    get_location_verification_service,
    require_dispatcher_id,
)
from raahat.application.location import LocationVerificationService
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates

router = APIRouter(prefix="/incidents/{incident_id}/location", tags=["locations"])


class VerifyLocationRequest(BaseModel):
    """Payload to confirm or supply an incident's verified location."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: Optional[uuid.UUID] = None
    coordinates: Optional[PointCoordinates] = None
    candidate_label: Optional[str] = None
    uncertainty_radius_m: Optional[float] = Field(default=None, ge=0.0)
    notes: Optional[str] = None


class VerifyLocationResponse(BaseModel):
    """Response returned upon successful dispatcher location verification."""

    incident_id: uuid.UUID
    verified_hypothesis: LocationHypothesis
    audit_event_id: uuid.UUID
    total_hypotheses: int


class LocationHypothesesResponse(BaseModel):
    """Historical candidate hypotheses for an incident."""

    incident_id: uuid.UUID
    total: int
    hypotheses: list[LocationHypothesis]


@router.post(
    "/verify",
    response_model=VerifyLocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify an incident's geographic location",
)
def verify_incident_location(
    incident_id: uuid.UUID,
    payload: VerifyLocationRequest,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: LocationVerificationService = Depends(get_location_verification_service),
) -> VerifyLocationResponse:
    """Record dispatcher confirmation of an incident location.

    Requires an authenticated dispatcher ID in the X-Dispatcher-Id header.
    Preserves all existing candidate hypotheses in the database without deletion.
    Creates a tamper-evident cryptographic audit log record.
    """
    if payload.hypothesis_id is None and payload.coordinates is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either hypothesis_id or coordinates must be provided",
        )

    try:
        result = service.verify_location(
            incident_id=incident_id,
            dispatcher_id=dispatcher_id,
            hypothesis_id=payload.hypothesis_id,
            coordinates=payload.coordinates,
            candidate_label=payload.candidate_label,
            uncertainty_radius_m=payload.uncertainty_radius_m,
            notes=payload.notes,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc).strip("'\""),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return VerifyLocationResponse(
        incident_id=result.incident_id,
        verified_hypothesis=result.verified_hypothesis,
        audit_event_id=result.audit_event_id,
        total_hypotheses=len(result.all_hypotheses),
    )


@router.get(
    "/hypotheses",
    response_model=LocationHypothesesResponse,
    status_code=status.HTTP_200_OK,
    summary="Get candidate location hypotheses history",
)
def get_incident_location_hypotheses(
    incident_id: uuid.UUID,
    service: LocationVerificationService = Depends(get_location_verification_service),
) -> LocationHypothesesResponse:
    """Retrieve full historical chain of candidate location hypotheses for an incident."""
    try:
        hypotheses = service.get_hypotheses_history(incident_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc).strip("'\""),
        ) from exc

    return LocationHypothesesResponse(
        incident_id=incident_id,
        total=len(hypotheses),
        hypotheses=hypotheses,
    )
