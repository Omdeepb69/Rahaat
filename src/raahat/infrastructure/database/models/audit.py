"""Audit event database model with cryptographic hash chaining."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEventModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_entity_idx", "entity_type", "entity_id"),
        Index("audit_created_idx", "created_at"),
    )

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
