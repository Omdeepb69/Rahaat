"""Outbound callback scheduler enforcing consent and retry limits."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from raahat.infrastructure.telephony.models import (
    CallbackJob,
    CallbackStatus,
    CallStatus,
)
from raahat.infrastructure.telephony.provider import TelephonyProvider
from raahat.infrastructure.telephony.repository import CallbackJobRepository

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class CallbackScheduler:
    """Schedules, regulates, and executes automated outbound callbacks.

    Enforces:
    1. Consent checks: calls without explicit caller consent are never dialed and
       transition directly to CANCELLED_NO_CONSENT.
    2. Retry limits: exponential backoff on busy/failed dials, transitioning to
       EXHAUSTED when retry_count reaches max_retries. Zero infinite redial loops.
    3. Auditability: full timestamping and provider call SID tracking.
    """

    def __init__(
        self,
        repository: CallbackJobRepository,
        provider: TelephonyProvider,
        caller_id: str = "+911077000000",
        base_backoff_seconds: int = 30,
        default_max_retries: int = 3,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.caller_id = caller_id
        self.base_backoff_seconds = base_backoff_seconds
        self.default_max_retries = default_max_retries

    def schedule_callback(
        self,
        disaster_id: uuid.UUID,
        phone_number: str,
        consent_given: bool,
        delay_seconds: int = 0,
        max_retries: Optional[int] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> CallbackJob:
        """Schedule an outbound callback with consent enforcement."""
        now = _now_utc()
        retries_limit = max_retries if max_retries is not None else self.default_max_retries

        if not consent_given:
            logger.info("Callback rejected for %s: caller consent not granted", phone_number)
            job = CallbackJob(
                id=uuid.uuid4(),
                disaster_id=disaster_id,
                phone_number=phone_number,
                consent_given=False,
                status=CallbackStatus.CANCELLED_NO_CONSENT,
                scheduled_at=now,
                created_at=now,
                max_retries=retries_limit,
                retry_count=0,
                completed_at=now,
                failure_reason="Caller consent was not provided",
                context=context or {},
            )
            return self.repository.save(job)

        scheduled_time = now + timedelta(seconds=delay_seconds)
        job = CallbackJob(
            id=uuid.uuid4(),
            disaster_id=disaster_id,
            phone_number=phone_number,
            consent_given=True,
            status=CallbackStatus.SCHEDULED,
            scheduled_at=scheduled_time,
            created_at=now,
            max_retries=retries_limit,
            retry_count=0,
            context=context or {},
        )
        return self.repository.save(job)

    async def process_single_job(
        self,
        job: CallbackJob,
        now: Optional[datetime] = None,
    ) -> CallbackJob:
        """Execute or progress one callback job through the lifecycle state machine."""
        current_time = now or _now_utc()

        # 1. Strict consent barrier
        if not job.consent_given:
            updated = CallbackJob(
                id=job.id,
                disaster_id=job.disaster_id,
                phone_number=job.phone_number,
                consent_given=False,
                status=CallbackStatus.CANCELLED_NO_CONSENT,
                scheduled_at=job.scheduled_at,
                created_at=job.created_at,
                max_retries=job.max_retries,
                retry_count=job.retry_count,
                last_attempted_at=current_time,
                completed_at=current_time,
                failure_reason="Caller consent was not provided",
                context=job.context,
            )
            return self.repository.update(updated)

        # 2. Infinite redial loop barrier
        if job.retry_count >= job.max_retries:
            logger.warning(
                "Callback job %s exceeded max retries (%d/%d); marking EXHAUSTED",
                job.id,
                job.retry_count,
                job.max_retries,
            )
            updated = CallbackJob(
                id=job.id,
                disaster_id=job.disaster_id,
                phone_number=job.phone_number,
                consent_given=job.consent_given,
                status=CallbackStatus.EXHAUSTED,
                scheduled_at=job.scheduled_at,
                created_at=job.created_at,
                max_retries=job.max_retries,
                retry_count=job.retry_count,
                last_attempted_at=current_time,
                completed_at=current_time,
                failure_reason=f"Exhausted maximum retry attempts ({job.max_retries})",
                context=job.context,
            )
            return self.repository.update(updated)

        # 3. Dial attempt via provider abstraction
        try:
            dial_result = await self.provider.dial(
                phone_number=job.phone_number,
                caller_id=self.caller_id,
                context=job.context,
            )

            if dial_result.status in (CallStatus.COMPLETED, CallStatus.CONNECTED, CallStatus.IN_PROGRESS):
                logger.info(
                    "Callback job %s successfully connected via provider (SID %s)",
                    job.id,
                    dial_result.call_sid,
                )
                updated = CallbackJob(
                    id=job.id,
                    disaster_id=job.disaster_id,
                    phone_number=job.phone_number,
                    consent_given=job.consent_given,
                    status=CallbackStatus.COMPLETED,
                    scheduled_at=job.scheduled_at,
                    created_at=job.created_at,
                    max_retries=job.max_retries,
                    retry_count=job.retry_count,
                    last_attempted_at=current_time,
                    completed_at=current_time,
                    provider_call_id=dial_result.call_sid,
                    failure_reason=None,
                    context=job.context,
                )
                return self.repository.update(updated)

            # Failure / busy / no-answer handling
            return self._handle_dial_failure(
                job=job,
                current_time=current_time,
                reason=dial_result.error_message or f"Dial status was {dial_result.status.value}",
                call_sid=dial_result.call_sid,
            )

        except Exception as exc:
            logger.exception("Dial exception during callback job %s: %s", job.id, exc)
            return self._handle_dial_failure(
                job=job,
                current_time=current_time,
                reason=str(exc),
                call_sid=None,
            )

    def _handle_dial_failure(
        self,
        job: CallbackJob,
        current_time: datetime,
        reason: str,
        call_sid: Optional[str],
    ) -> CallbackJob:
        new_retry_count = job.retry_count + 1

        if new_retry_count >= job.max_retries:
            status = CallbackStatus.EXHAUSTED
            completed_at = current_time
            next_scheduled = job.scheduled_at
        else:
            status = CallbackStatus.SCHEDULED
            completed_at = None
            # Exponential backoff: base * 2^(retry_count)
            backoff_seconds = self.base_backoff_seconds * (2 ** job.retry_count)
            next_scheduled = current_time + timedelta(seconds=backoff_seconds)

        updated = CallbackJob(
            id=job.id,
            disaster_id=job.disaster_id,
            phone_number=job.phone_number,
            consent_given=job.consent_given,
            status=status,
            scheduled_at=next_scheduled,
            created_at=job.created_at,
            max_retries=job.max_retries,
            retry_count=new_retry_count,
            last_attempted_at=current_time,
            completed_at=completed_at,
            provider_call_id=call_sid,
            failure_reason=reason,
            context=job.context,
        )
        return self.repository.update(updated)

    async def process_due_jobs(
        self,
        now: Optional[datetime] = None,
        limit: int = 10,
    ) -> list[CallbackJob]:
        """Claim and execute due callbacks."""
        current_time = now or _now_utc()
        claimed = self.repository.claim_due_jobs(now=current_time, limit=limit)
        results: list[CallbackJob] = []

        for job in claimed:
            res = await self.process_single_job(job, now=current_time)
            results.append(res)

        return results
