"""Field app data models and sync value objects."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SyncStatus(str, Enum):
    """Synchronization status of an offline report."""

    LOCALLY_SAVED = "locally_saved"
    SYNCING = "syncing"
    SERVER_SYNCHRONIZED = "server_synchronized"
    FAILED = "failed"


class OfflineReportDraft(BaseModel):
    """Volunteer input payload when drafting a report in the field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    disaster_id: uuid.UUID
    raw_payload: dict[str, Any]
    source_identity: Optional[str] = None
    language_code: Optional[str] = None
    client_created_at: datetime = Field(default_factory=utc_now)


class OfflineReport(BaseModel):
    """Locally persisted offline report with monotonic device sequence number."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    device_id: uuid.UUID
    sequence: int = Field(..., ge=1, description="Strictly monotonic sequence per device")
    disaster_id: uuid.UUID
    raw_payload: dict[str, Any]
    source_identity: Optional[str] = None
    language_code: Optional[str] = None
    client_created_at: datetime = Field(default_factory=utc_now)
    idempotency_key: str
    sync_status: SyncStatus = SyncStatus.LOCALLY_SAVED
    batch_id: Optional[uuid.UUID] = None
    synced_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SyncReportItem(BaseModel):
    """Wire item contained in an outbound sync batch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID
    sequence: int
    disaster_id: uuid.UUID
    raw_payload: dict[str, Any]
    client_created_at: datetime
    idempotency_key: str
    source_identity: Optional[str] = None
    language_code: Optional[str] = None


class SyncBatch(BaseModel):
    """Outbound batch of offline reports queued for server synchronization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: uuid.UUID
    batch_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    from_sequence: int
    to_sequence: int
    items: list[SyncReportItem]

    @property
    def count(self) -> int:
        return len(self.items)


class SyncAck(BaseModel):
    """Server receipt acknowledgement confirming synchronization up to a sequence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: uuid.UUID
    batch_id: uuid.UUID
    server_synced_at: datetime
    acknowledged_sequence: int
    accepted_count: int
    duplicate_count: int = 0

