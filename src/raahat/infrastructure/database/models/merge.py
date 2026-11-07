"""Entity merge event database model for reversible resolution."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EntityMergeEventModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "entity_merge_events"

    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

