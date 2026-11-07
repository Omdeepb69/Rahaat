"""Report domain entities and value objects."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..shared.enums import ProcessingStatus, SourceType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportSubmission(BaseModel):
    """Incoming report submission payload from any input channel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    disaster_id: uuid.UUID
    source_type: SourceType
    source_event_id: Optional[str] = None
    source_identity: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    channel_reference: Optional[str] = None
    raw_payload: dict[str, Any]
    client_created_at: Optional[datetime] = None
    language_code: Optional[str] = None
    idempotency_key: Optional[str] = None

    def to_report(self, report_id: Optional[uuid.UUID] = None) -> Report:
        computed_key = self.idempotency_key or f"{self.source_type.value}-{self.source_event_id or uuid.uuid4().hex}"
        return Report(
            id=report_id or uuid.uuid4(),
            disaster_id=self.disaster_id,
            source_type=self.source_type,
            source_event_id=self.source_event_id,
            source_identity=self.source_identity,
            device_id=self.device_id,
            channel_reference=self.channel_reference,
            raw_payload=self.raw_payload,
            received_at=utc_now(),
            client_created_at=self.client_created_at,
            language_code=self.language_code,
            processing_status=ProcessingStatus.PENDING,
            idempotency_key=computed_key,
        )


class Report(BaseModel):
    """Immutable incoming distress report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    disaster_id: uuid.UUID
    source_type: SourceType
    source_event_id: Optional[str] = None
    source_identity: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    channel_reference: Optional[str] = None
    raw_payload: dict[str, Any]
    received_at: datetime = Field(default_factory=utc_now)
    client_created_at: Optional[datetime] = None
    language_code: Optional[str] = None
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    idempotency_key: str

