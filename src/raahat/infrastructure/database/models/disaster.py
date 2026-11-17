"""Disaster (an "operation" in the operator interface) database model."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography, Geometry
from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DisasterModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "disasters"
    __table_args__ = (
        Index("disasters_boundary_geo_idx", "boundary", postgresql_using="gist"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    disaster_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    area_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # LGD codes of the jurisdiction that owns this operation. Only accounts for
    # that jurisdiction (or its state, or national) can see it.
    state_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    district_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    # A standing operation receives public reports for a district when no
    # named operation is active there.
    is_standing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    boundary: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    # Operator-supplied map focus for the operation. Not derived or guessed.
    map_center: Mapped[Optional[Any]] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
