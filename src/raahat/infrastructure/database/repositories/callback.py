"""Callback job repository protocol and PostgreSQL / in-memory implementations."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.database.models.callback import CallbackJobModel
from raahat.infrastructure.telephony.models import CallbackJob, CallbackStatus
from raahat.infrastructure.telephony.repository import CallbackJobRepository

logger = logging.getLogger(__name__)


def _model_to_job(model: CallbackJobModel) -> CallbackJob:
    return CallbackJob(
        id=model.id,
        disaster_id=model.disaster_id,
        phone_number=model.phone_number,
        consent_given=model.consent_given,
        status=CallbackStatus(model.status),
        scheduled_at=model.scheduled_at,
        created_at=model.created_at,
        max_retries=model.max_retries,
        retry_count=model.retry_count,
        last_attempted_at=model.last_attempted_at,
        completed_at=model.completed_at,
        provider_call_id=model.provider_call_id,
        failure_reason=model.failure_reason,
        context=dict(model.payload) if model.payload else {},
    )


class PostgresCallbackJobRepository(CallbackJobRepository):
    """PostgreSQL-backed implementation of CallbackJobRepository."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, job: CallbackJob) -> CallbackJob:
        with self._session_factory() as session:
            model = CallbackJobModel(
                id=job.id,
                disaster_id=job.disaster_id,
                phone_number=job.phone_number,
                consent_given=job.consent_given,
                status=job.status.value,
                retry_count=job.retry_count,
                max_retries=job.max_retries,
                scheduled_at=job.scheduled_at,
                last_attempted_at=job.last_attempted_at,
                completed_at=job.completed_at,
                provider_call_id=job.provider_call_id,
                failure_reason=job.failure_reason,
                payload=job.context,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _model_to_job(model)

    def get_by_id(self, job_id: uuid.UUID) -> Optional[CallbackJob]:
        with self._session_factory() as session:
            model = session.get(CallbackJobModel, job_id)
            if not model:
                return None
            return _model_to_job(model)

    def claim_due_jobs(self, now: datetime, limit: int = 10) -> list[CallbackJob]:
        with self._session_factory() as session:
            stmt = (
                select(CallbackJobModel)
                .where(
                    CallbackJobModel.status.in_([CallbackStatus.PENDING.value, CallbackStatus.SCHEDULED.value]),
                    CallbackJobModel.scheduled_at <= now,
                )
                .with_for_update(skip_locked=True)
                .order_by(CallbackJobModel.scheduled_at.asc())
                .limit(limit)
            )
            models = list(session.scalars(stmt).all())
            jobs: list[CallbackJob] = []
            for model in models:
                model.status = CallbackStatus.DIALING.value
                model.last_attempted_at = now
                session.add(model)
                jobs.append(_model_to_job(model))
            session.commit()
            return jobs

    def update(self, job: CallbackJob) -> CallbackJob:
        with self._session_factory() as session:
            model = session.get(CallbackJobModel, job.id)
            if not model:
                raise ValueError(f"CallbackJob {job.id} not found for update")

            model.status = job.status.value
            model.retry_count = job.retry_count
            model.max_retries = job.max_retries
            model.scheduled_at = job.scheduled_at
            model.last_attempted_at = job.last_attempted_at
            model.completed_at = job.completed_at
            model.provider_call_id = job.provider_call_id
            model.failure_reason = job.failure_reason
            model.payload = job.context

            session.commit()
            session.refresh(model)
            return _model_to_job(model)

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        status: Optional[CallbackStatus] = None,
        limit: int = 50,
    ) -> list[CallbackJob]:
        with self._session_factory() as session:
            stmt = (
                select(CallbackJobModel)
                .where(CallbackJobModel.disaster_id == disaster_id)
            )
            if status is not None:
                stmt = stmt.where(CallbackJobModel.status == status.value)
            stmt = stmt.order_by(CallbackJobModel.scheduled_at.asc()).limit(limit)
            models = session.scalars(stmt).all()
            return [_model_to_job(m) for m in models]

    def count_by_status(self, disaster_id: uuid.UUID) -> dict[str, int]:
        with self._session_factory() as session:
            stmt = (
                select(CallbackJobModel.status, func.count(CallbackJobModel.id))
                .where(CallbackJobModel.disaster_id == disaster_id)
                .group_by(CallbackJobModel.status)
            )
            results = session.execute(stmt).all()
            counts = {row[0]: row[1] for row in results}
            for s in CallbackStatus:
                counts.setdefault(s.value, 0)
            return counts


class InMemoryCallbackJobRepository(CallbackJobRepository):
    """In-memory callback job repository for tests and local simulation."""

    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, CallbackJob] = {}

    def save(self, job: CallbackJob) -> CallbackJob:
        self.jobs[job.id] = job
        return job

    def get_by_id(self, job_id: uuid.UUID) -> Optional[CallbackJob]:
        return self.jobs.get(job_id)

    def claim_due_jobs(self, now: datetime, limit: int = 10) -> list[CallbackJob]:
        due: list[CallbackJob] = []
        for job in list(self.jobs.values()):
            if job.status in (CallbackStatus.PENDING, CallbackStatus.SCHEDULED):
                # Ensure tz-aware comparison
                job_time = job.scheduled_at
                current_time = now
                if job_time.tzinfo is None:
                    job_time = job_time.replace(tzinfo=timezone.utc)
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)

                if job_time <= current_time:
                    claimed = CallbackJob(
                        id=job.id,
                        disaster_id=job.disaster_id,
                        phone_number=job.phone_number,
                        consent_given=job.consent_given,
                        status=CallbackStatus.DIALING,
                        scheduled_at=job.scheduled_at,
                        created_at=job.created_at,
                        max_retries=job.max_retries,
                        retry_count=job.retry_count,
                        last_attempted_at=now,
                        completed_at=job.completed_at,
                        provider_call_id=job.provider_call_id,
                        failure_reason=job.failure_reason,
                        context=job.context,
                    )
                    self.jobs[job.id] = claimed
                    due.append(claimed)
                    if len(due) >= limit:
                        break
        return due

    def update(self, job: CallbackJob) -> CallbackJob:
        if job.id not in self.jobs:
            raise ValueError(f"CallbackJob {job.id} not found in in-memory repository")
        self.jobs[job.id] = job
        return job

    def list_by_disaster(
        self,
        disaster_id: uuid.UUID,
        status: Optional[CallbackStatus] = None,
        limit: int = 50,
    ) -> list[CallbackJob]:
        matches = [
            j for j in self.jobs.values()
            if j.disaster_id == disaster_id and (status is None or j.status == status)
        ]
        matches.sort(key=lambda j: j.scheduled_at)
        return matches[:limit]

    def count_by_status(self, disaster_id: uuid.UUID) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in CallbackStatus}
        for j in self.jobs.values():
            if j.disaster_id == disaster_id:
                counts[j.status.value] = counts.get(j.status.value, 0) + 1
        return counts
