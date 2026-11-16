"""Incident, IncidentReport and IncidentLink database models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

INCIDENT_STATUSES = (
    "unverified",
    "under_review",
    "verified",
    "assigned",
    "in_progress",
    "resolved",
    "closed",
    "duplicate",
)


class IncidentModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('unverified','under_review','verified','assigned',"
            "'in_progress','resolved','closed','duplicate')",
            name="incidents_status_valid",
        ),
        CheckConstraint(
            "location_confidence IS NULL OR (location_confidence >= 0.0 AND location_confidence <= 1.0)",
            name="incidents_location_confidence_range",
        ),
        Index("incidents_reference_key", "reference", unique=True),
        Index("incidents_disaster_status_idx", "disaster_id", "status", "created_at"),
        Index("incidents_location_geo_idx", "location", postgresql_using="gist"),
    )

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Human-readable identifier, e.g. INC-000042. Assigned from a sequence.
    reference: Mapped[str] = mapped_column(
        String(24),
        server_default=text("'INC-' || lpad(nextval('incident_reference_seq')::text, 6, '0')"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="unverified", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_channel: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    operational_priority: Mapped[str] = mapped_column(
        String(32),
        default="unassessed",
        nullable=False,
    )
    # Facts derived from report evidence. Machine-produced.
    severity_facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Operator corrections: {field: {"value": ..., "by": uuid, "at": iso}}.
    # These take precedence over severity_facts and are never produced by a model.
    fact_overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    # Last triage assessment: reasons, unknown fields, source, timestamp.
    triage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Best current position, denormalised from location_hypotheses so that
    # lists and map queries do not need a join per incident.
    location_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[Any]] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    # none | candidate | confirmed
    location_status: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    location_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    location_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_uncertainty_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_hypothesis_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    merged_into_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
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
    __table_args__ = (Index("incident_reports_report_idx", "report_id"),)

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
        Index("incident_links_status_idx", "status", "created_at"),
        Index("incident_links_a_idx", "incident_a_id"),
        Index("incident_links_b_idx", "incident_b_id"),
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
    # Why the two incidents were considered related: one entry per signal with
    # its name, weight and the evidence that triggered it.
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
