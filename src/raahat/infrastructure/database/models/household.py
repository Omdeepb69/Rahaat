"""Household and Person database models."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class HouseholdModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "households"

    disaster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disasters.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    identity_status: Mapped[str] = mapped_column(
        String(32),
        default="unverified",
        nullable=False,
    )

    persons = relationship("PersonModel", back_populates="household", cascade="all, delete-orphan")


class PersonModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "persons"

    household_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="SET NULL"),
        nullable=True,
    )
    display_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vulnerability_attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    identity_status: Mapped[str] = mapped_column(
        String(32),
        default="unverified",
        nullable=False,
    )

    household = relationship("HouseholdModel", back_populates="persons")
