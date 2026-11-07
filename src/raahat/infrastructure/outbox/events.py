"""Domain event value object and outbox job status enumeration."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class OutboxJobStatus(str, Enum):
    """Lifecycle states for an outbox job row."""

    PENDING = "pending"
    CLAIMED = "claimed"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILURE = "retryable_failure"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class DomainEvent:
    """Immutable record of a domain event to be published via the outbox.

    The aggregate_type + aggregate_id pair identifies which domain object
    the event belongs to.  event_type is a dot-separated string such as
    'report.received' or 'incident.status_changed'.
    """

    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

