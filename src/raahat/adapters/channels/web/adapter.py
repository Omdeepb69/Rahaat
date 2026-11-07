"""Web SOS channel adapter.

Converts public Web SOS form submissions into normalized ReportSubmissions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType


class WebSOSPayload(BaseModel):
    """Payload submitted from the Web SOS public portal."""

    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    caller_name: Optional[str] = Field(default=None, max_length=255)
    phone_number: Optional[str] = Field(default=None, max_length=64)
    location_text: Optional[str] = Field(default=None, max_length=512)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    people_count: Optional[int] = Field(default=None, ge=1)
    situation_description: str = Field(..., min_length=1)
    needs: list[str] = Field(default_factory=list)
    language_code: Optional[str] = Field(default=None, max_length=16)
    submission_token: Optional[str] = Field(default=None, max_length=255)


class WebSOSAdapter:
    """Transforms Web SOS submissions into domain ReportSubmission objects."""

    @staticmethod
    def to_submission(payload: WebSOSPayload | dict[str, Any]) -> ReportSubmission:
        if isinstance(payload, dict):
            validated = WebSOSPayload.model_validate(payload)
        else:
            validated = payload

        raw: dict[str, Any] = {
            "caller_name": validated.caller_name,
            "phone_number": validated.phone_number,
            "location_text": validated.location_text,
            "latitude": validated.latitude,
            "longitude": validated.longitude,
            "people_count": validated.people_count,
            "situation_description": validated.situation_description,
            "needs": validated.needs,
        }

        # Idempotency key derived from client submission_token if provided
        idempotency_key = (
            f"web-{validated.submission_token}"
            if validated.submission_token
            else None
        )

        return ReportSubmission(
            disaster_id=validated.disaster_id,
            source_type=SourceType.WEB,
            source_identity=validated.phone_number or validated.caller_name,
            source_event_id=validated.submission_token,
            channel_reference="web_sos",
            raw_payload=raw,
            client_created_at=datetime.now(timezone.utc),
            language_code=validated.language_code,
            idempotency_key=idempotency_key,
        )

