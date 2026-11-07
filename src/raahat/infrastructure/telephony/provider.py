"""Telephony provider protocol and stub implementation."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional, Protocol

from .models import CallStatus, DialResult

logger = logging.getLogger(__name__)


class TelephonyProvider(Protocol):
    """Protocol for external telephony engines (Twilio, Exotel, Asterisk, etc.).

    Decouples outbound dialing and call management from core domain logic.
    """

    async def dial(
        self,
        phone_number: str,
        caller_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> DialResult: ...

    async def hangup(self, call_sid: str) -> None: ...

    async def get_call_status(self, call_sid: str) -> CallStatus: ...


class StubTelephonyProvider(TelephonyProvider):
    """Configurable in-memory telephony provider for testing and offline development."""

    def __init__(
        self,
        default_status: CallStatus = CallStatus.COMPLETED,
        should_fail: bool = False,
        failure_error: str = "Provider gateway unreachable",
    ) -> None:
        self.default_status = default_status
        self.should_fail = should_fail
        self.failure_error = failure_error
        self.dial_history: list[dict[str, Any]] = []
        self.call_states: dict[str, CallStatus] = {}

    async def dial(
        self,
        phone_number: str,
        caller_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> DialResult:
        sid = f"call_{uuid.uuid4().hex[:12]}"

        record = {
            "call_sid": sid,
            "phone_number": phone_number,
            "caller_id": caller_id,
            "context": context or {},
        }
        self.dial_history.append(record)

        if self.should_fail:
            status = CallStatus.FAILED
            self.call_states[sid] = status
            return DialResult(
                call_sid=sid,
                status=status,
                error_message=self.failure_error,
            )

        self.call_states[sid] = self.default_status
        return DialResult(
            call_sid=sid,
            status=self.default_status,
        )

    async def hangup(self, call_sid: str) -> None:
        if call_sid in self.call_states:
            self.call_states[call_sid] = CallStatus.CANCELED

    async def get_call_status(self, call_sid: str) -> CallStatus:
        return self.call_states.get(call_sid, CallStatus.FAILED)

