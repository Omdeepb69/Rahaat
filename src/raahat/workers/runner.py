"""Database-backed outbox worker with row-level leasing and fencing tokens.

Design
------
The worker loop runs three phases per tick:

1. **Claim** — SELECT … FOR UPDATE SKIP LOCKED on PENDING rows whose lease
   has expired (or is null).  Each claimed row gets a fresh ``lease_token``
   (UUID4) and a ``lease_expires_at`` deadline.  The token is returned to the
   caller as a *fencing token*; every subsequent write for that job MUST
   include the same token.  A worker that lost its lease (crashed and
   restarted, or took too long) will find the token mismatched and discard its
   stale result.

2. **Process** — The claimed job is handed to the registered ``OutboxJobHandler``.
   The handler is called *outside* of an open DB transaction (ARCHITECTURE.md
   §4: "NEVER hold an open transaction while waiting on … external API calls").
   The handler returns either success or raises an exception.

3. **Settle** — A new short transaction records the outcome:
   - Success      → status = SUCCEEDED, processed_at = now
   - Failure      → retry_count += 1; if retry_count >= max_retries,
                    status = DEAD_LETTER; else status = RETRYABLE_FAILURE,
                    lease cleared (eligible for re-claim next tick).
   All writes are gated on the original ``lease_token`` matching the row's
   current token (fencing guard).

Stale lease recovery
--------------------
Any CLAIMED/PROCESSING row whose ``lease_expires_at`` is in the past is
treated as PENDING again at the next claim phase, allowing a healthy worker
to take over.  This is automatic — the WHERE clause in the claim query already
selects them.

``OutboxRepository`` protocol
------------------------------
All DB interactions go through the ``OutboxRepository`` protocol.  This keeps
the state-machine logic dependency-free and unit-testable with a pure-Python
fake.  ``PostgresOutboxRepository`` is the production implementation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from raahat.infrastructure.outbox import ClaimResult, OutboxJob, OutboxRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Handler protocol
# ---------------------------------------------------------------------------


class OutboxJobHandler(Protocol):
    """Process one outbox job.

    Implementations must be idempotent: they may be called more than once for
    the same event if a worker crashed after claiming but before settling.
    Raise any exception to signal processing failure (triggers retry/dead-letter).
    """

    def __call__(self, job: OutboxJob) -> None: ...


# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------


@dataclass
class OutboxWorkerConfig:
    """Tunable parameters for the OutboxWorker loop."""

    batch_size: int = 10
    lease_duration: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    poll_interval_s: float = 1.0
    max_retries: int = 5


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class OutboxWorker:
    """Background worker that relays outbox events with leasing and fencing.

    Usage::

        worker = OutboxWorker(
            repository=PostgresOutboxRepository(session_factory),
            handler=my_relay_handler,
            config=OutboxWorkerConfig(batch_size=5, max_retries=3),
        )
        worker.run_once()   # process one batch (useful in tests / cron)
        worker.run(stop_event)  # loop until stop_event.is_set()
    """

    def __init__(
        self,
        repository: OutboxRepository,
        handler: OutboxJobHandler,
        config: OutboxWorkerConfig | None = None,
    ) -> None:
        self._repo = repository
        self._handler = handler
        self._cfg = config or OutboxWorkerConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> int:
        """Claim and process one batch.  Returns the number of jobs processed."""
        claims = self._repo.claim_pending_batch(
            batch_size=self._cfg.batch_size,
            lease_duration=self._cfg.lease_duration,
        )
        for claim in claims:
            self._process(claim)
        return len(claims)

    def run(self, stop_event: Any) -> None:  # stop_event: threading.Event
        """Loop until ``stop_event.is_set()``, sleeping between empty polls."""
        while not stop_event.is_set():
            processed = self.run_once()
            if processed == 0:
                # No work available; back off to avoid tight-loop on idle.
                time.sleep(self._cfg.poll_interval_s)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process(self, claim: ClaimResult) -> None:
        job = claim.job
        logger.info(
            "Processing outbox job",
            extra={
                "job_id": str(job.id),
                "event_type": job.event_type,
                "retry_count": job.retry_count,
            },
        )
        try:
            self._handler(job)
        except Exception:
            logger.exception(
                "Outbox job failed",
                extra={"job_id": str(job.id), "retry_count": job.retry_count},
            )
            updated = self._repo.mark_failed(
                job_id=job.id,
                lease_token=claim.lease_token,
                new_retry_count=job.retry_count + 1,
                max_retries=self._cfg.max_retries,
            )
            if not updated:
                logger.warning(
                    "Lease stolen before failure settlement; discarding stale result",
                    extra={"job_id": str(job.id)},
                )
            return

        processed_at = datetime.now(timezone.utc)
        updated = self._repo.mark_succeeded(
            job_id=job.id,
            lease_token=claim.lease_token,
            processed_at=processed_at,
        )
        if not updated:
            logger.warning(
                "Lease stolen before success settlement; discarding stale result",
                extra={"job_id": str(job.id)},
            )
        else:
            logger.info(
                "Outbox job succeeded",
                extra={"job_id": str(job.id), "event_type": job.event_type},
            )
