"""Resource database model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

RESOURCE_TYPES = (
    "boat",
    "ambulance",
    "medical_team",
    "rescue_team",
    "vehicle",
    "helicopter",
    "shelter",
    "other",
)
RESOURCE_STATUSES = ("available", "assigned", "maintenance", "offline")
POSITION_SOURCES = ("operator", "device_gps", "integration")


class ResourceModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        Index("resources_geo_idx", "location", postgresql_using="gist"),
        Index("resources_disaster_status_idx", "disaster_id", "availability_status"),
        Index("resources_disaster_callsign_key", "disaster_id", "callsign", unique=True),
        CheckConstraint(
            "availability_status IN ('available','assigned','maintenance','offline')",
            name="resources_status_valid",
        ),
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="resources_capacity_nonnegative"),
        CheckConstraint(
            "(location IS NULL) = (position_updated_at IS NULL)",
            name="resources_position_has_timestamp",
        ),
    )

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Short operational identifier used on the radio and in the interface.
    callsign: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # People the resource can carry or treat in one trip; NULL when not applicable.
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crew_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    availability_status: Mapped[str] = mapped_column(
        String(32),
        default="available",
        nullable=False,
    )
    status_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Last known position, with where it came from and when. A position
    # without a timestamp cannot be stored.
    location: Mapped[Optional[Any]] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    position_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    position_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position_accuracy_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    is_retired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    disaster = relationship("DisasterModel")
