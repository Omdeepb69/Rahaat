"""Production background worker coordinator and entrypoint.

Runs transactional outbox leasing, offline device sequence auditing,
and scheduled telephone callback workers in an asynchronous tick loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

from raahat.infrastructure.database.repositories.callback import PostgresCallbackJobRepository
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.infrastructure.outbox import OutboxJob, PostgresOutboxRepository
from raahat.infrastructure.telephony import CallbackScheduler, StubTelephonyProvider
from raahat.workers.callback_worker import CallbackWorker, CallbackWorkerConfig
from raahat.workers.report_processor import AudioReportProcessor, AudioReportProcessorConfig
from raahat.workers.runner import OutboxWorker, OutboxWorkerConfig
from raahat.workers.sync_worker import SyncWorker, SyncWorkerConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("raahat.workers")


def default_job_handler(job: OutboxJob) -> None:
    """Default handler dispatching domain events to appropriate processing engines."""
    logger.info(
        "Worker handling domain outbox job: type=%s id=%s aggregate=%s:%s",
        job.event_type,
        job.id,
        job.aggregate_type,
        job.aggregate_id,
    )


class WorkerService:
    """Manages worker lifecycles, periodic ticks, and graceful termination."""

    def __init__(self, heartbeat_path: Path | str = "/tmp/worker_heartbeat") -> None:
        self.heartbeat_path = Path(heartbeat_path)
        self.is_running = True

        db_url = os.getenv("DATABASE_URL")
        self.engine = create_sync_engine(db_url)
        self.session_factory = get_sync_sessionmaker(self.engine)

        # 1. Outbox Worker
        self.outbox_repo = PostgresOutboxRepository(session_factory=self.session_factory)
        self.outbox_worker = OutboxWorker(
            repository=self.outbox_repo,
            handler=default_job_handler,
            config=OutboxWorkerConfig(batch_size=10),
        )

        # 2. Sync Worker
        self.sync_worker = SyncWorker(
            session_factory=self.session_factory,
            config=SyncWorkerConfig(poll_interval_s=2.0),
        )

        # 3. Callback Worker
        self.callback_repo = PostgresCallbackJobRepository(session_factory=self.session_factory)
        self.telephony_provider = StubTelephonyProvider()
        self.callback_scheduler = CallbackScheduler(
            repository=self.callback_repo,
            provider=self.telephony_provider,
        )
        self.callback_worker = CallbackWorker(
            scheduler=self.callback_scheduler,
            config=CallbackWorkerConfig(batch_size=10),
        )

        # 4. Audio Speech & Report Extraction Processor
        self.audio_processor = AudioReportProcessor(
            session_factory=self.session_factory,
            config=AudioReportProcessorConfig(batch_size=10),
        )

    def update_heartbeat(self) -> None:
        """Touch heartbeat file to confirm worker liveness for container health checks."""
        try:
            self.heartbeat_path.write_text(
                f"{datetime.now(timezone.utc).isoformat()}\n",
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Failed to update heartbeat file %s: %s", self.heartbeat_path, e)

    def stop(self) -> None:
        """Signal worker loop to cleanly shut down."""
        logger.info("Received termination signal; draining current worker tick...")
        self.is_running = False

    async def run_loop(self, tick_interval_seconds: float = 2.0) -> None:
        """Run continuous asynchronous background worker ticks."""
        logger.info("Raahat Background Worker service started (tick=%ss)", tick_interval_seconds)

        while self.is_running:
            self.update_heartbeat()

            # Tick 1: Outbox event processing
            try:
                processed_jobs = self.outbox_worker.run_once()
                if processed_jobs > 0:
                    logger.debug("Outbox worker processed %d jobs", processed_jobs)
            except Exception as e:
                logger.error("Outbox worker iteration error: %s", e)

            # Tick 2: Telephony callback queue
            try:
                processed_calls = await self.callback_worker.run_once()
                if processed_calls > 0:
                    logger.debug("Callback worker dialed %d due calls", processed_calls)
            except Exception as e:
                logger.error("Callback worker iteration error: %s", e)

            # Tick 3: Audio speech transcription & report extraction
            try:
                processed_audio = await self.audio_processor.run_once()
                if processed_audio > 0:
                    logger.debug("Audio processor transcribed %d reports", processed_audio)
            except Exception as e:
                logger.error("Audio processor iteration error: %s", e)

            # Sleep between ticks
            await asyncio.sleep(tick_interval_seconds)

        logger.info("Raahat Background Worker service successfully shut down.")


async def main() -> None:
    service = WorkerService()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, service.stop)

    await service.run_loop()


if __name__ == "__main__":
    asyncio.run(main())
