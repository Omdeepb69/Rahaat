"""Audit inspection and tamper verification API routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from raahat.api.dependencies import get_audit_service, require_dispatcher_id
from raahat.infrastructure.audit import (
    AuditService,
    ChainVerificationResult,
)
from raahat.infrastructure.database.models.audit import AuditEventModel

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    """Read-only audit event representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID
    action: str
    actor_id: Optional[uuid.UUID]
    entity_type: str
    entity_id: uuid.UUID
    prev_hash: Optional[str]
    hash: str
    payload: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    """Paginated list of audit events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AuditEventResponse]
    total: int
    limit: int
    offset: int


class ChainVerificationResponse(BaseModel):
    """Response detailing the cryptographic verification of an entity's audit chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    entity_id: uuid.UUID
    is_valid: bool
    total_events: int
    genesis_hash: Optional[str] = None
    latest_hash: Optional[str] = None
    error_message: Optional[str] = None
    corrupted_event_id: Optional[uuid.UUID] = None
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None


class GlobalVerificationResponse(BaseModel):
    """Response detailing global verification across all audit chains in the system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    all_valid: bool
    total_entities: int
    total_events: int
    corrupted_chains: list[ChainVerificationResponse] = Field(default_factory=list)


def _to_event_response(model: AuditEventModel) -> AuditEventResponse:
    return AuditEventResponse(
        id=model.id,
        action=model.action,
        actor_id=model.actor_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        prev_hash=model.prev_hash,
        hash=model.hash,
        payload=dict(model.payload) if model.payload else {},
        created_at=model.created_at,
    )


def _to_chain_response(res: ChainVerificationResult) -> ChainVerificationResponse:
    return ChainVerificationResponse(
        entity_type=res.entity_type,
        entity_id=res.entity_id,
        is_valid=res.is_valid,
        total_events=res.total_events,
        genesis_hash=res.genesis_hash,
        latest_hash=res.latest_hash,
        error_message=res.error_message,
        corrupted_event_id=res.corrupted_event_id,
        expected_hash=res.expected_hash,
        actual_hash=res.actual_hash,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/events",
    response_model=AuditEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query audit events with filtering and pagination",
)
def list_audit_events(
    entity_type: Optional[str] = Query(None, description="Filter by target entity type"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Filter by target entity ID"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    actor_id: Optional[uuid.UUID] = Query(None, description="Filter by actor ID"),
    limit: int = Query(50, ge=1, le=200, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: AuditService = Depends(get_audit_service),
) -> AuditEventListResponse:
    """Read-only inspection of audit events."""
    items, total = service.query_events(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        items=[_to_event_response(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/events/{event_id}",
    response_model=AuditEventResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single audit event by ID",
)
def get_audit_event(
    event_id: uuid.UUID,
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: AuditService = Depends(get_audit_service),
) -> AuditEventResponse:
    """Retrieve details of a single tamper-evident audit record."""
    event = service.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit event {event_id} not found",
        )
    return _to_event_response(event)


@router.get(
    "/verify",
    response_model=Union[ChainVerificationResponse, GlobalVerificationResponse],
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic hash chain integrity",
)
def verify_audit_chain(
    entity_type: Optional[str] = Query(None, description="Target entity type to verify"),
    entity_id: Optional[uuid.UUID] = Query(None, description="Target entity ID to verify"),
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    service: AuditService = Depends(get_audit_service),
) -> Union[ChainVerificationResponse, GlobalVerificationResponse]:
    """Verify cryptographic SHA-256 hash chaining and tamper-evidence.

    - If both entity_type and entity_id are specified: verifies that entity's audit chain.
    - If neither is specified: performs a global verification of all entity chains.
    - If only one is specified: returns 400 Bad Request.
    """
    if (entity_type is not None and entity_id is None) or (entity_type is None and entity_id is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both entity_type and entity_id must be provided to verify an entity chain, or omit both for global verification.",
        )

    if entity_type is not None and entity_id is not None:
        result = service.verify_entity_chain(entity_type=entity_type, entity_id=entity_id)
        return _to_chain_response(result)

    global_result = service.verify_all_chains()
    return GlobalVerificationResponse(
        all_valid=global_result.all_valid,
        total_entities=global_result.total_entities,
        total_events=global_result.total_events,
        corrupted_chains=[_to_chain_response(c) for c in global_result.corrupted_chains],
    )
