"""Audit verification data models."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChainVerificationResult(BaseModel):
    """Result of cryptographic hash-chain verification for a specific entity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_type: str
    entity_id: uuid.UUID
    is_valid: bool
    total_events: int
    genesis_hash: Optional[str] = None
    latest_hash: Optional[str] = None
    error_message: Optional[str] = None
    corrupted_event_id: Optional[uuid.UUID] = None
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None


class GlobalVerificationResult(BaseModel):
    """Result of global cryptographic verification across all audit entities."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    all_valid: bool
    total_entities: int
    total_events: int
    corrupted_chains: list[ChainVerificationResult] = Field(default_factory=list)

