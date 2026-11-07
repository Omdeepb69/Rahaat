"""Repository protocol for CallbackJob persistence."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Protocol

from .models import CallbackJob, CallbackStatus


class CallbackJobRepository(Protocol):
    """Protocol for persisting, claiming, and updating callback jobs."""

    def save(self, job: CallbackJob) -> CallbackJob: ...

    def get_by_id(self, job_id: uuid.UUID) -> Optional[CallbackJob]: ...

    def claim_due_jobs(self, now: datetime, limit: int = 10) -> list[CallbackJob]: ...

    def update(self, job: CallbackJob) -> CallbackJob: ...

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        status: Optional[CallbackStatus] = None,
        limit: int = 50,
    ) -> list[CallbackJob]: ...

    def count_by_status(self, disaster_id: uuid.UUID) -> dict[str, int]: ...
