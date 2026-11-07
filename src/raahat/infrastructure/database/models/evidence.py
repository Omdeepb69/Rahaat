"""Evidence items and spans database models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceItemModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_items"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="evidence_items_confidence_range",
        ),
        Index("evidence_report_idx", "report_id"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    attribute: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    spans = relationship("EvidenceSpanModel", back_populates="evidence_item", cascade="all, delete-orphan")


class EvidenceSpanModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "evidence_spans"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_start_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_reference: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    evidence_item = relationship("EvidenceItemModel", back_populates="spans")

