"""Live event models and payload sanitization for real-time streaming."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mask_phone_number(phone: str) -> str:
    """Mask a telephone number to preserve privacy while keeping dialing prefixes."""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) >= 6:
        # Keep leading characters, mask middle/tail leaving only prefix and last 2 digits
        return phone[: min(len(phone) - 4, 6)] + "****" + phone[-2:]
    return "***"


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize event payload: recursively mask phone numbers and remove sensitive fields."""
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = key.lower()
        if "secret" in key_lower or "token" in key_lower or "credential" in key_lower or "password" in key_lower:
            continue

        if isinstance(value, dict):
            sanitized[key] = sanitize_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str) and (
            "phone" in key_lower or "mobile" in key_lower or "caller" in key_lower or "contact" in key_lower
        ):
            sanitized[key] = mask_phone_number(value)
        else:
            sanitized[key] = value

    return sanitized


@dataclass(frozen=True)
class LiveEvent:
    """An event dispatched in real time to operator consoles via SSE."""

    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    disaster_id: Optional[uuid.UUID] = None
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_at: datetime = field(default_factory=utc_now)

    def format_sse(self) -> str:
        """Format event into a compliant W3C Server-Sent Event message string."""
        clean_payload = sanitize_payload(self.payload)
        data = {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id),
            "disaster_id": str(self.disaster_id) if self.disaster_id else None,
            "occurred_at": self.occurred_at.isoformat(),
            "payload": clean_payload,
        }
        return (
            f"id: {self.event_id}\n"
            f"event: {self.event_type}\n"
            f"data: {json.dumps(data, sort_keys=True, default=str)}\n\n"
        )

