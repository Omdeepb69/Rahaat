"""Incident, IncidentReport and IncidentLink database models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class IncidentModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incidents"

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    operational_priority: Mapped[str] = mapped_column(
        String(32),
        default="unassessed",
        nullable=False,
    )
    severity_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    reports = sa_relationship("IncidentReportModel", back_populates="incident", cascade="all, delete-orphan")
    hypotheses = sa_relationship("LocationHypothesisModel", back_populates="incident", cascade="all, delete-orphan")


class IncidentReportModel(Base):
    __tablename__ = "incident_reports"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    linked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    incident = sa_relationship("IncidentModel", back_populates="reports")
    report = sa_relationship("ReportModel", lazy="joined")


class IncidentLinkModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incident_links"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="incident_links_confidence_range",
        ),
    )

    incident_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
