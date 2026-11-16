"""Audit trail: activity log and hash-chain verification."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.deps import CurrentUser, get_db, get_session_factory, require
from raahat.api.schemas import Page, Pagination
from raahat.infrastructure.audit import AuditVerifier, PostgresAuditRepository
from raahat.infrastructure.database.models.audit import AuditEventModel
from raahat.infrastructure.database.models.user import UserModel
from raahat.security.permissions import Permission

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntry(BaseModel):
    seq: int
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    incident_id: Optional[uuid.UUID]
    disaster_id: Optional[uuid.UUID]
    actor_id: Optional[uuid.UUID]
    actor_name: Optional[str]
    occurred_at: datetime
    payload: dict[str, Any]
    hash: str
    prev_hash: Optional[str]


class ChainCheck(BaseModel):
    verified: bool
    entities_checked: int
    events_checked: int
    broken: list[dict[str, Any]]
    checked_at: datetime


@router.get("/events", response_model=Page[AuditEntry], summary="Activity log")
def list_events(
    disaster_id: Optional[uuid.UUID] = Query(None),
    entity_type: Optional[str] = Query(None, max_length=64),
    action_prefix: Optional[str] = Query(None, max_length=64, description="e.g. 'dispatch.'"),
    actor_id: Optional[uuid.UUID] = Query(None),
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.AUDIT_READ)),
    session: Session = Depends(get_db),
) -> Page[AuditEntry]:
    conditions = []
    if disaster_id is not None:
        conditions.append(AuditEventModel.disaster_id == disaster_id)
    if entity_type:
        conditions.append(AuditEventModel.entity_type == entity_type)
    if action_prefix:
        conditions.append(AuditEventModel.action.startswith(action_prefix))
    if actor_id is not None:
        conditions.append(AuditEventModel.actor_id == actor_id)
    total = session.execute(select(func.count(AuditEventModel.id)).where(*conditions)).scalar_one()
    rows = session.execute(
        select(AuditEventModel, UserModel.full_name)
        .outerjoin(UserModel, UserModel.id == AuditEventModel.actor_id)
        .where(*conditions)
        .order_by(AuditEventModel.seq.desc())
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page(
        items=[
            AuditEntry(
                seq=e.seq, id=e.id, action=e.action, entity_type=e.entity_type, entity_id=e.entity_id,
                incident_id=e.incident_id, disaster_id=e.disaster_id, actor_id=e.actor_id,
                actor_name=name, occurred_at=e.created_at, payload=e.payload or {},
                hash=e.hash, prev_hash=e.prev_hash,
            )
            for e, name in rows
        ],
        total=total, limit=page.limit, offset=page.offset,
    )


@router.get("/verify", response_model=ChainCheck, summary="Recompute and check every audit hash chain")
def verify(
    _: CurrentUser = Depends(require(Permission.AUDIT_READ)),
    factory: sessionmaker[Session] = Depends(get_session_factory),
) -> ChainCheck:
    """Recomputes each entity's chain from stored content. A mismatch means a record was altered or removed."""
    result = AuditVerifier().verify_all_chains(PostgresAuditRepository(factory))
    broken = [
        {
            "entity_type": chain.entity_type,
            "entity_id": str(chain.entity_id),
            "failure": chain.error_message,
            "event_id": str(chain.corrupted_event_id) if chain.corrupted_event_id else None,
        }
        for chain in result.corrupted_chains
    ]
    return ChainCheck(
        verified=result.all_valid, entities_checked=result.total_entities,
        events_checked=result.total_events, broken=broken, checked_at=datetime.now().astimezone(),
    )
