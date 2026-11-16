"""User accounts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

USER_ROLES = ("admin", "operator", "dispatcher", "resource_coordinator", "observer")


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin','operator','dispatcher','resource_coordinator','observer')",
            name="users_role_valid",
        ),
        Index("users_username_lower_key", func.lower(text("username")), unique=True),
    )

    username: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Incremented on password change or deactivation; tokens carrying an older
    # value are rejected.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
