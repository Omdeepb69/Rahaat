"""Background worker.

One process, one loop. Each tick it writes a heartbeat row and processes a
bounded batch of waiting reports: transcription for audio, initial analysis
for channel reports, and model enrichment where configured.

Bounded by design for an 8 GB host: one report at a time, at most
``WORKER_BATCH_SIZE`` per tick, no in-memory queue. The queue is the
``reports`` table, so nothing is lost if the process stops; on start, reports
left ``claimed`` by a previous run are returned to the queue.
"""
from __future__ import annotations

import logging
import os
import signal
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.ai.registry import build_providers
from raahat.application.alerts import service as alerts
from raahat.application.intake import service as intake
from raahat.application.intake.pipeline import ReportPipeline
from raahat.application.system.status import record_integration_result
from raahat.config import Settings, get_settings
from raahat.domain.shared.enums import ProcessingStatus
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.models.system import WorkerHeartbeatModel
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker
from raahat.logging_config import configure_logging

logger = logging.getLogger("raahat.worker")

WORKER_NAME = "report-worker"
ALERT_POLL_SECONDS = 300
_CLAIM = text(
    """
    UPDATE reports SET processing_status = 'claimed'
    WHERE id IN (
        SELECT id FROM reports
        WHERE processing_status IN ('pending', 'pending_enrichment')
        ORDER BY received_at ASC
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Worker:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        pipeline: Optional[ReportPipeline] = None,
    ) -> None:
        self._settings = settings
        self._sessions = session_factory
        self._providers = build_providers(settings)
        self._pipeline = pipeline or ReportPipeline(
            settings=settings, providers=self._providers, session_factory=session_factory
        )
        self._next_alert_poll = 0.0
        self._stop = threading.Event()
        self._started_at = _now()
        self._processed = 0
        self._failed = 0

    def stop(self, *_: object) -> None:
        logger.info("Stop requested; finishing the current report")
        self._stop.set()

    # ---------------------------------------------------------------- recovery
    def recover(self) -> int:
        """Return reports abandoned mid-processing by a previous run to the queue."""
        with self._sessions() as session:
            count = session.execute(
                text(
                    "UPDATE reports SET processing_status = CASE WHEN EXISTS ("
                    "SELECT 1 FROM incident_reports ir WHERE ir.report_id = reports.id) "
                    "THEN 'pending_enrichment' ELSE 'pending' END "
                    "WHERE processing_status = 'claimed'"
                )
            ).rowcount
            session.commit()
        if count:
            logger.warning("Returned %d interrupted report(s) to the queue", count)
        return count or 0

    # --------------------------------------------------------------- heartbeat
    def heartbeat(self) -> None:
        with self._sessions() as session:
            statement = insert(WorkerHeartbeatModel).values(
                worker_name=WORKER_NAME,
                pid=os.getpid(),
                started_at=self._started_at,
                last_beat_at=_now(),
                details={"processed_total": self._processed, "failed_total": self._failed},
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[WorkerHeartbeatModel.worker_name],
                    set_={
                        "pid": statement.excluded.pid,
                        "started_at": statement.excluded.started_at,
                        "last_beat_at": statement.excluded.last_beat_at,
                        "details": statement.excluded.details,
                    },
                )
            )
            session.commit()

    # -------------------------------------------------------------- processing
    def claim(self) -> list[uuid.UUID]:
        with self._sessions() as session:
            ids = [row.id for row in session.execute(_CLAIM, {"limit": self._settings.worker_batch_size})]
            session.commit()
        return ids

    def process(self, report_id: uuid.UUID) -> bool:
        """Run every outstanding stage for one report in one transaction."""
        self._pipeline.provider_results.clear()
        with self._sessions() as session:
            report = session.get(ReportModel, report_id)
            if report is None:
                return False
            try:
                if report.original_text is None:
                    path = intake.audio_path(self._settings.audio_storage_dir, report)
                    if path is not None:
                        self._pipeline.transcribe(session, report, path.read_bytes())
                self._pipeline.analyse(session, report)
                if self._pipeline.enrichment_available:
                    self._pipeline.enrich(session, report)
                report.processing_status = ProcessingStatus.PROCESSED.value
                report.processed_at = _now()
                for key, ok, detail, latency in self._pipeline.provider_results:
                    record_integration_result(session, key, ok=ok, detail=detail, latency_ms=latency)
                session.commit()
                return True
            except Exception as exc:
                session.rollback()
                logger.exception("Processing failed for report %s", report_id)
                self._mark_failed(report_id, f"{type(exc).__name__}: {exc}")
                return False

    def _mark_failed(self, report_id: uuid.UUID, error: str) -> None:
        with self._sessions() as session:
            report = session.get(ReportModel, report_id)
            if report is None:
                return
            report.processing_status = ProcessingStatus.FAILED.value
            report.processing_error = error[:1000]
            append_audit(
                session,
                action="report.processing_failed",
                actor_id=None,
                entity_type="report",
                entity_id=report.id,
                disaster_id=report.disaster_id,
                payload={"error": error[:300]},
            )
            session.commit()

    def poll_alerts(self) -> None:
        """Read the official alert feed at most every ALERT_POLL_SECONDS."""
        if not self._providers.alerts.configured or time.monotonic() < self._next_alert_poll:
            return
        self._next_alert_poll = time.monotonic() + ALERT_POLL_SECONDS
        try:
            with self._sessions() as session:
                result = alerts.poll(session, self._providers.alerts)
            if result.get("stored"):
                logger.info("Imported %d alert(s)", result["stored"])
        except Exception:
            logger.exception("Alert feed poll failed")

    def run_once(self) -> int:
        self.heartbeat()
        self.poll_alerts()
        handled = 0
        for report_id in self.claim():
            if self.process(report_id):
                self._processed += 1
            else:
                self._failed += 1
            handled += 1
            if self._stop.is_set():
                break
        if handled:
            self.heartbeat()
        return handled

    def run_forever(self) -> None:
        self.recover()
        logger.info(
            "Worker started (tick %.1fs, batch %d, enrichment %s)",
            self._settings.worker_tick_seconds,
            self._settings.worker_batch_size,
            "on" if self._pipeline.enrichment_available else "off",
        )
        while not self._stop.is_set():
            try:
                handled = self.run_once()
            except Exception:
                # Database unavailable or similar: keep the process alive and retry.
                logger.exception("Worker tick failed")
                handled = 0
            if not handled:
                self._stop.wait(self._settings.worker_tick_seconds)
        logger.info("Worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_sync_engine(settings.database_url)
    worker = Worker(settings, get_sync_sessionmaker(engine))
    signal.signal(signal.SIGTERM, worker.stop)
    signal.signal(signal.SIGINT, worker.stop)
    try:
        worker.run_forever()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
