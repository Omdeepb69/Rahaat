"""Location hypotheses and Landmarks database models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LocationHypothesisModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "location_hypotheses"
    __table_args__ = (
        CheckConstraint(
            "probability IS NULL OR (probability >= 0.0 AND probability <= 1.0)",
            name="location_hypotheses_probability_range",
        ),
        Index("location_hypotheses_geo_idx", "location", postgresql_using="gist"),
        Index("location_hypotheses_incident_idx", "incident_id", "created_at"),
        CheckConstraint(
            "source IN ('caller_gps','operator','geocoder','landmark','unknown')",
            name="location_hypotheses_source_valid",
        ),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    candidate_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_evidence_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uncertainty_radius_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default="unverified",
        nullable=False,
    )

    # How this position was obtained. These are not interchangeable:
    #   caller_gps  device position supplied with the report
    #   operator    entered or placed on the map by an authorised user
    #   geocoder    returned by an external geocoding service for a text query
    #   landmark    matched against the landmark gazetteer from a description
    #   unknown     recorded before provenance was tracked
    source: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    # Provider name, query text, matched landmark id, similarity score, etc.
    source_detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    incident = relationship("IncidentModel", back_populates="hypotheses")
    source_evidence = relationship("EvidenceItemModel")


class LandmarkModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "landmarks"
    __table_args__ = (
        Index("landmarks_geo_idx", "location", postgresql_using="gist"),
        Index("landmarks_name_idx", "name"),
        Index(
            "landmarks_source_external_key",
            "source",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "landmarks_name_trgm_idx",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # osm | operator — where the record came from. Imported rows keep their
    # upstream identifier in external_id and licence details in metadata.
    source: Mapped[str] = mapped_column(String(32), default="operator", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    salience: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
