"""Resource database model."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResourceModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "resources"
    __table_args__ = (
        Index("resources_geo_idx", "location", postgresql_using="gist"),
    )

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    availability_status: Mapped[str] = mapped_column(
        String(32),
        default="available",
        nullable=False,
    )
    location: Mapped[Optional[Any]] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=True,
    )

    disaster = relationship("DisasterModel")
