"""Household and Person domain models."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import IdentityStatus


class Person(BaseModel):
    """Individual person potentially affected by a disaster."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    household_id: Optional[uuid.UUID] = None
    display_label: Optional[str] = None
    vulnerability_attributes: dict[str, Any] = Field(default_factory=dict)
    identity_status: IdentityStatus = IdentityStatus.UNVERIFIED


class Household(BaseModel):
    """Household cluster of individuals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    disaster_id: uuid.UUID
    display_label: Optional[str] = None
    identity_status: IdentityStatus = IdentityStatus.UNVERIFIED
    members: tuple[Person, ...] = Field(default_factory=tuple)

