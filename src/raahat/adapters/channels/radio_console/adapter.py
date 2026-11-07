"""Radio operator console channel adapter.

Converts manual reports entered by radio dispatchers monitoring VHF/HF channels
into normalized ReportSubmissions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType


class RadioConsolePayload(BaseModel):
    """Payload representing a report transcribed by a human radio operator."""

    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    operator_callsign: str = Field(..., min_length=2, max_length=64, description="Radio operator callsign")
    frequency_channel: str = Field(..., min_length=2, max_length=64, description="Radio channel (e.g. VHF-CH16)")
    transmission_text: str = Field(..., min_length=1, description="Message heard on radio")
    reporting_party: Optional[str] = Field(default=None, max_length=128, description="Callsign/name of reporting party")
    estimated_location: Optional[str] = Field(default=None, max_length=512)
    people_count: Optional[int] = Field(default=None, ge=1)
    operator_entry_id: Optional[str] = Field(default=None, max_length=255, description="Client console entry ID")
    operator_notes: Optional[str] = None


class RadioConsoleAdapter:
    """Transforms radio console operator entries into domain ReportSubmission objects."""

    @staticmethod
    def to_submission(payload: RadioConsolePayload | dict[str, Any]) -> ReportSubmission:
        if isinstance(payload, dict):
            validated = RadioConsolePayload.model_validate(payload)
        else:
            validated = payload

        raw: dict[str, Any] = {
            "operator_callsign": validated.operator_callsign,
            "frequency_channel": validated.frequency_channel,
            "transmission_text": validated.transmission_text,
            "reporting_party": validated.reporting_party,
            "estimated_location": validated.estimated_location,
            "people_count": validated.people_count,
            "operator_notes": validated.operator_notes,
            "operator_entry_id": validated.operator_entry_id,
        }

        idempotency_key = (
            f"radio-{validated.operator_entry_id}"
            if validated.operator_entry_id
            else None
        )

        return ReportSubmission(
            disaster_id=validated.disaster_id,
            source_type=SourceType.RADIO,
            source_identity=validated.operator_callsign,
            source_event_id=validated.operator_entry_id,
            channel_reference=validated.frequency_channel,
            raw_payload=raw,
            client_created_at=datetime.now(timezone.utc),
            language_code=None,
            idempotency_key=idempotency_key,
        )
