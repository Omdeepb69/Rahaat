"""Disaster database model."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Index, String
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
    boundary: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
