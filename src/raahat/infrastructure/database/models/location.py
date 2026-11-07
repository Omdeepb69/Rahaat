"""Location hypotheses and Landmarks database models."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String
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

    incident = relationship("IncidentModel", back_populates="hypotheses")
    source_evidence = relationship("EvidenceItemModel")


class LandmarkModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "landmarks"
    __table_args__ = (
        Index("landmarks_geo_idx", "location", postgresql_using="gist"),
        Index("landmarks_name_idx", "name"),
    )

    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    salience: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    location: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
