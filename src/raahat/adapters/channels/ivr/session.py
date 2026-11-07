"""IVR call session state and data model."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.speech import Transcript


class IVRCallState(str, Enum):
    """Finite state machine states for an interactive disaster voice session."""

    INIT = "init"
    AWAITING_LOCATION = "awaiting_location"
    AWAITING_LOCATION_KEYPAD = "awaiting_location_keypad"
    AWAITING_PEOPLE_COUNT = "awaiting_people_count"
    AWAITING_PEOPLE_COUNT_READBACK = "awaiting_people_count_readback"
    AWAITING_NEEDS = "awaiting_needs"
    COMPLETED = "completed"
    TERMINATED = "terminated"


@dataclass
class IVRCallSession:
    """Maintains state across multi-turn telephone dialogs."""

    call_sid: str
    disaster_id: uuid.UUID
    caller_phone: str
    current_state: IVRCallState = IVRCallState.INIT
    turn_count: int = 0
    state_retries: int = 0
    max_turns: int = 10
    max_state_retries: int = 2
    low_confidence_threshold: float = 0.5

    # Collected disaster distress attributes
    location_text: Optional[str] = None
    location_code_dtmf: Optional[str] = None
    people_count: Optional[int] = None
    people_count_unconfirmed: Optional[int] = None
    people_count_confirmed: bool = False
    situation_description: Optional[str] = None
    needs: list[str] = field(default_factory=list)
    language_code: str = "hi"

    # Audio & DTMF logs
    transcripts: list[Transcript] = field(default_factory=list)
    dtmf_history: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_submission(self) -> ReportSubmission:
        """Converts completed session into a canonical ReportSubmission.

        Crucial Architectural Boundary: The IVR channel produces a ReportSubmission
        for the ingestion gateway; it never mutates incidents or allocates resources.
        """
        raw_payload: dict[str, Any] = {
            "call_sid": self.call_sid,
            "caller_phone": self.caller_phone,
            "turns_taken": self.turn_count,
            "location_text": self.location_text,
            "location_code_dtmf": self.location_code_dtmf,
            "people_count": self.people_count,
            "people_count_confirmed": self.people_count_confirmed,
            "situation_description": self.situation_description,
            "needs": self.needs,
            "dtmf_inputs": list(self.dtmf_history),
            "transcripts": [
                {"text": t.text, "confidence": t.confidence, "language": t.language}
                for t in self.transcripts
            ],
        }

        # Idempotency key per call_sid ensures retransmitted webhooks don't duplicate
        idempotency_key = f"ivr-{self.call_sid}"

        return ReportSubmission(
            disaster_id=self.disaster_id,
            source_type=SourceType.IVR,
            source_identity=self.caller_phone,
            source_event_id=self.call_sid,
            channel_reference="ivr_voice_session",
            raw_payload=raw_payload,
            client_created_at=self.created_at,
            language_code=self.language_code,
            idempotency_key=idempotency_key,
        )
