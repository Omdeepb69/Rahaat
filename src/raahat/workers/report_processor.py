"""Background audio report processing worker.

Leases and processes pending voice distress reports:
1. Reads audio recording from durable storage.
2. Performs Voice Activity Detection (VAD) and speech transcription (Whisper/fallback).
3. Updates report processing_status to 'extracted' and populates transcript.
4. Emits transactional outbox event 'report.extracted' for downstream triage and SSE streams.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from raahat.adapters.channels.ivr.vad import EnergyVADDetector, VADDetector
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.outbox import DomainEvent, EventOutbox, PostgresEventOutbox
from raahat.infrastructure.speech import AudioInput, SpeechRecognizer, WhisperRecognizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioReportProcessorConfig:
    """Configuration for the AudioReportProcessor worker."""

    batch_size: int = 10
    default_sample_rate: int = 16000


class AudioReportProcessor:
    """Processes pending audio reports by transcribing speech and updating report records."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        speech_recognizer: Optional[SpeechRecognizer] = None,
        vad_detector: Optional[VADDetector] = None,
        outbox: Optional[EventOutbox] = None,
        config: Optional[AudioReportProcessorConfig] = None,
    ) -> None:
        self.session_factory = session_factory
        self.speech_recognizer = speech_recognizer or WhisperRecognizer(allow_fallback=True)
        self.vad_detector = vad_detector or EnergyVADDetector()
        self.outbox = outbox or PostgresEventOutbox()
        self.config = config or AudioReportProcessorConfig()

    async def process_report(self, report_id: uuid.UUID) -> bool:
        """Process a single report by transcribing its audio and updating database state."""
        with self.session_factory() as session:
            report = session.get(ReportModel, report_id)
            if not report or report.processing_status != "pending":
                return False

            raw_payload = dict(report.raw_payload or {})
            audio_meta = raw_payload.get("audio")

            # If report has no audio metadata, it's a text report (SMS/web)
            if not audio_meta or not isinstance(audio_meta, dict):
                # Transition text reports directly to extracted
                raw_payload["text"] = raw_payload.get("text") or raw_payload.get("situation_description", "")
                report.raw_payload = raw_payload
                report.processing_status = "extracted"
                flag_modified(report, "raw_payload")

                if self.outbox:
                    self.outbox.publish(
                        DomainEvent(
                            event_type="report.extracted",
                            aggregate_type="report",
                            aggregate_id=report.id,
                            payload={
                                "report_id": str(report.id),
                                "disaster_id": str(report.disaster_id),
                                "text": raw_payload.get("text", ""),
                                "has_speech": False,
                                "source_type": report.source_type,
                            },
                        ),
                        session=session,
                    )
                session.commit()
                return True

            # Extract audio bytes from storage path or payload
            audio_path_str = audio_meta.get("path")
            audio_bytes: bytes = b""

            if audio_path_str:
                audio_path = Path(audio_path_str)
                if audio_path.exists():
                    try:
                        audio_bytes = audio_path.read_bytes()
                    except OSError as e:
                        logger.warning("Failed to read audio file %s for report %s: %s", audio_path, report_id, e)

            if not audio_bytes and "audio_bytes" in audio_meta:
                # Direct embedded bytes (testing fallback)
                raw_embedded = audio_meta["audio_bytes"]
                if isinstance(raw_embedded, str):
                    audio_bytes = raw_embedded.encode("utf-8")
                elif isinstance(raw_embedded, bytes):
                    audio_bytes = raw_embedded

            # Build AudioInput
            sample_rate = audio_meta.get("sample_rate", self.config.default_sample_rate)
            duration_ms = audio_meta.get("duration_ms")
            audio_input = AudioInput(
                audio_bytes=audio_bytes,
                sample_rate=sample_rate,
                duration_ms=duration_ms,
            )

            # 1. Voice Activity Detection
            has_speech = self.vad_detector.detect_speech(audio_input)

            # 2. Speech Transcription
            try:
                transcript = await self.speech_recognizer.transcribe(
                    audio_input,
                    language_hint=report.language_code,
                )
            except Exception as e:
                logger.error("Transcription error on report %s: %s", report_id, e)
                report.processing_status = "failed"
                raw_payload["error"] = f"Transcription failed: {e}"
                report.raw_payload = raw_payload
                flag_modified(report, "raw_payload")
                session.commit()
                return False

            # 3. Update report with extracted transcript
            raw_payload["transcript"] = transcript.text
            raw_payload["transcript_confidence"] = transcript.confidence
            raw_payload["transcript_language"] = transcript.language
            raw_payload["has_speech"] = has_speech
            raw_payload["speech_processed_at"] = datetime.now(timezone.utc).isoformat()

            # Ensure 'text' field is populated for downstream entity resolution and triage
            existing_text = raw_payload.get("text")
            if not existing_text or existing_text == "Voice SOS report submitted via citizen portal":
                raw_payload["text"] = transcript.text or raw_payload.get("situation_description", "Voice report")

            report.raw_payload = raw_payload
            report.processing_status = "extracted"
            flag_modified(report, "raw_payload")

            # 4. Transactional Outbox Event
            if self.outbox:
                self.outbox.publish(
                    DomainEvent(
                        event_type="report.extracted",
                        aggregate_type="report",
                        aggregate_id=report.id,
                        payload={
                            "report_id": str(report.id),
                            "disaster_id": str(report.disaster_id),
                            "transcript": transcript.text,
                            "confidence": transcript.confidence,
                            "has_speech": has_speech,
                            "source_type": report.source_type,
                            "source_identity": report.source_identity,
                        },
                    ),
                    session=session,
                )

            session.commit()
            logger.info("Transcribed audio report %s: '%s' (confidence=%.2f)", report_id, transcript.text, transcript.confidence)
            return True

    async def process_pending_reports(self, limit: Optional[int] = None) -> int:
        """Find pending reports and process them sequentially."""
        effective_limit = limit or self.config.batch_size
        with self.session_factory() as session:
            stmt = (
                select(ReportModel.id)
                .where(ReportModel.processing_status == "pending")
                .order_by(ReportModel.received_at.asc())
                .limit(effective_limit)
            )
            report_ids = list(session.scalars(stmt).all())

        if not report_ids:
            return 0

        processed = 0
        for report_id in report_ids:
            try:
                success = await self.process_report(report_id)
                if success:
                    processed += 1
            except Exception as e:
                logger.error("Unexpected error processing report %s: %s", report_id, e)

        return processed

    async def run_once(self) -> int:
        """Single tick entrypoint for worker loop."""
        return await self.process_pending_reports()
