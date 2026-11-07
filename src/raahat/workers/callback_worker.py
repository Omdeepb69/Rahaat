"""Background worker for executing scheduled telephony callbacks."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from raahat.infrastructure.telephony.scheduler import CallbackScheduler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CallbackWorkerConfig:
    """Tunable parameters for the CallbackWorker."""

    poll_interval_s: float = 1.0
    batch_size: int = 10


class CallbackWorker:
    """Asynchronous worker that polls and executes due outbound callbacks.

    Usage::

        worker = CallbackWorker(scheduler, CallbackWorkerConfig(poll_interval_s=2.0))
        await worker.run_once()  # process one batch
        await worker.run(stop_event)  # loop until stop_event is set
    """

    def __init__(
        self,
        scheduler: CallbackScheduler,
        config: Optional[CallbackWorkerConfig] = None,
    ) -> None:
        self.scheduler = scheduler
        self.config = config or CallbackWorkerConfig()

    async def run_once(self) -> int:
        """Process one batch of due callback jobs.

        Returns:
            The number of callback jobs claimed and processed.
        """
        jobs = await self.scheduler.process_due_jobs(limit=self.config.batch_size)
        if jobs:
            logger.info("CallbackWorker processed %d due callback jobs", len(jobs))
        return len(jobs)

    async def run(self, stop_event: Any) -> None:  # stop_event: asyncio.Event or threading.Event
        """Continuously poll and execute callbacks until ``stop_event.is_set()``."""
        logger.info("Starting CallbackWorker poll loop")
        while not stop_event.is_set():
            try:
                processed = await self.run_once()
                if processed == 0:
                    await asyncio.sleep(self.config.poll_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error in CallbackWorker tick: %s", exc)
                await asyncio.sleep(self.config.poll_interval_s)
        logger.info("CallbackWorker poll loop terminated")

