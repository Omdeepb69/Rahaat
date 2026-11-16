"""Report database model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDPrimaryKeyMixin, utc_now


class ReportModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("disaster_id", "idempotency_key", name="reports_disaster_idempotency_key"),
        Index("reports_disaster_received_idx", "disaster_id", "received_at"),
        Index("reports_processing_status_idx", "processing_status", "received_at"),
    )

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_identity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    channel_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    client_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    language_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # The report's words exactly as received (typed text, or the speech
    # transcript). Never overwritten; translation is stored alongside.
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    language_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    language_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    translated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translation_provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Caller identity is held in explicit columns so access control and
    # retention can act on it without parsing channel payloads.
    caller_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    caller_contact: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    disaster = relationship("DisasterModel", lazy="joined")
