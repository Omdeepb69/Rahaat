"""Audit event model: the hash-chained, sequence-ordered record of every operational change.

The same table is the realtime event log. ``seq`` gives a total order that
matches commit order (writers serialise on an advisory lock before inserting),
so a client that has seen sequence N can ask for everything after N.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import BigInteger, Index, Sequence, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin

audit_seq = Sequence("audit_events_seq_seq", metadata=Base.metadata)


class AuditEventModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_entity_idx", "entity_type", "entity_id"),
        Index("audit_created_idx", "created_at"),
        Index("audit_events_seq_key", "seq", unique=True),
        Index("audit_events_incident_seq_idx", "incident_id", "seq"),
        Index("audit_events_disaster_seq_idx", "disaster_id", "seq"),
    )

    seq: Mapped[int] = mapped_column(
        BigInteger, audit_seq, server_default=audit_seq.next_value(), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Correlation keys for filtering the stream and building incident timelines.
    disaster_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
