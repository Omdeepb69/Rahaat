"""Guided voice call sessions from the public reporting site."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, utc_now


class VoiceCallModel(Base):
    __tablename__ = "voice_calls"
    __table_args__ = (
        CheckConstraint("status IN ('open','submitted','abandoned')", name="voice_calls_status_valid"),
        Index("voice_calls_open_idx", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # SHA-256 of the caller's session token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state_code: Mapped[str] = mapped_column(String(8), nullable=False)
    district_code: Mapped[str] = mapped_column(String(8), nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="hi", nullable=False)
    # default | detected | script | chosen
    language_source: Mapped[str] = mapped_column(String(16), default="default", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    step: Mapped[str] = mapped_column(String(32), nullable=False)
    slots: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    turns: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    client_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
