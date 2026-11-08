"""Disaster management and active disaster context API routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from raahat.api.dependencies import get_session_factory
from raahat.infrastructure.database.models.disaster import DisasterModel

router = APIRouter(prefix="/disasters", tags=["disasters"])


class DisasterResponse(BaseModel):
    """Public representation of a disaster emergency event."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    disaster_type: str
    status: str
    started_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@router.get(
    "",
    response_model=list[DisasterResponse],
    status_code=status.HTTP_200_OK,
    summary="List disasters",
)
def list_disasters(
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    session_factory=Depends(get_session_factory),
) -> list[DisasterResponse]:
    """List disaster events ordered by creation recency."""
    with session_factory() as session:
        stmt = (
            select(DisasterModel)
            .order_by(DisasterModel.created_at.desc())
            .limit(limit)
        )
        models = session.scalars(stmt).all()
        return [
            DisasterResponse(
                id=m.id,
                name=m.name,
                disaster_type=m.disaster_type,
                status=m.status,
                started_at=m.started_at,
                created_at=m.created_at,
            )
            for m in models
        ]


@router.get(
    "/active",
    response_model=DisasterResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current active disaster",
)
def get_active_disaster(
    session_factory=Depends(get_session_factory),
) -> DisasterResponse:
    """Retrieve the latest active disaster operational context."""
    with session_factory() as session:
        # First try active status
        stmt = (
            select(DisasterModel)
            .where(DisasterModel.status == "active")
            .order_by(DisasterModel.created_at.desc())
            .limit(1)
        )
        m = session.scalars(stmt).first()
        if not m:
            # Fallback to most recent disaster if status is not explicitly "active"
            stmt_fallback = (
                select(DisasterModel)
                .order_by(DisasterModel.created_at.desc())
                .limit(1)
            )
            m = session.scalars(stmt_fallback).first()

        if not m:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No disaster events registered in system",
            )

        return DisasterResponse(
            id=m.id,
            name=m.name,
            disaster_type=m.disaster_type,
            status=m.status,
            started_at=m.started_at,
            created_at=m.created_at,
        )


@router.get(
    "/{disaster_id}",
    response_model=DisasterResponse,
    status_code=status.HTTP_200_OK,
    summary="Get disaster detail",
)
def get_disaster_detail(
    disaster_id: uuid.UUID,
    session_factory=Depends(get_session_factory),
) -> DisasterResponse:
    """Retrieve disaster metadata by ID."""
    with session_factory() as session:
        m = session.get(DisasterModel, disaster_id)
        if not m:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Disaster {disaster_id} not found",
            )
        return DisasterResponse(
            id=m.id,
            name=m.name,
            disaster_type=m.disaster_type,
            status=m.status,
            started_at=m.started_at,
            created_at=m.created_at,
        )
