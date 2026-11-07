"""SMS channel adapter.

Converts inbound SMS messages (from telco gateways or aggregators) into
normalized ReportSubmissions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType


class SMSPayload(BaseModel):
    """Payload representing an inbound SMS message."""

    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    sender: str = Field(..., min_length=3, max_length=64, description="Sender phone number")
    message: str = Field(..., min_length=1, max_length=1600, description="SMS body text")
    message_id: Optional[str] = Field(default=None, max_length=255, description="Gateway message ID")
    shortcode: Optional[str] = Field(default=None, max_length=64, description="Target shortcode/number")
    received_at: Optional[datetime] = None


class SMSAdapter:
    """Transforms SMS gateway payloads into domain ReportSubmission objects."""

    @staticmethod
    def to_submission(payload: SMSPayload | dict[str, Any]) -> ReportSubmission:
        if isinstance(payload, dict):
            validated = SMSPayload.model_validate(payload)
        else:
            validated = payload

        raw: dict[str, Any] = {
            "sender": validated.sender,
            "message": validated.message,
            "message_id": validated.message_id,
            "shortcode": validated.shortcode,
        }

        idempotency_key = (
            f"sms-{validated.message_id}"
            if validated.message_id
            else None
        )

        return ReportSubmission(
            disaster_id=validated.disaster_id,
            source_type=SourceType.SMS,
            source_identity=validated.sender,
            source_event_id=validated.message_id,
            channel_reference=validated.shortcode or "sms_gateway",
            raw_payload=raw,
            client_created_at=validated.received_at or datetime.now(timezone.utc),
            language_code=None,
            idempotency_key=idempotency_key,
        )
