"""Telephony domain models and value objects."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class CallStatus(str, enum.Enum):
    """Lifecycle status of a telephone call."""

    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    CONNECTED = "connected"
    COMPLETED = "completed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    CANCELED = "canceled"


class CallbackStatus(str, enum.Enum):
    """Lifecycle state machine for an automated outbound callback."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    DIALING = "dialing"
    CONNECTED = "connected"
    COMPLETED = "completed"
    RETRYABLE_FAILURE = "retryable_failure"
    CANCELLED_NO_CONSENT = "cancelled_no_consent"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True)
class DialResult:
    """Outcome of an outbound dial attempt from a TelephonyProvider."""

    call_sid: str
    status: CallStatus
    error_message: Optional[str] = None


@dataclass(frozen=True)
class CallbackJob:
    """An outbound phone callback scheduled for a distress caller."""

    id: uuid.UUID
    disaster_id: uuid.UUID
    phone_number: str
    consent_given: bool
    status: CallbackStatus
    scheduled_at: datetime
    created_at: datetime
    max_retries: int = 3
    retry_count: int = 0
    last_attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    provider_call_id: Optional[str] = None
    failure_reason: Optional[str] = None
    context: dict[str, Any] = field(default_factory=dict)
