"""Automated Audio-to-Dispatch Orchestrator Service.

Chains the end-to-end emergency response pipeline:
Distress Audio / Report ID
  -> Speech Recognition & VAD (Whisper / Fallback)
  -> PostGIS Landmark Disambiguation & Spatial Bounding
  -> Report Ingestion & Structured Evidence Extraction
  -> Canonical Incident Resolution (Conservative Matcher / Auto-link)
  -> Deterministic Safety Policy Triage (P0-P3 explainability)
  -> Nearest Capable Rescue Resource Recommendation
  -> Dispatch Proposal (Human-in-the-loop authorization rule)
  -> Real-Time Server-Sent Events (SSE) Broadcast
  -> Citizen Ticket Tracking Status Advancement
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.adapters.channels.ivr.vad import EnergyVADDetector, VADDetector
from raahat.application.dispatch import DispatchService
from raahat.application.events import EventBroadcaster
from raahat.application.events.models import LiveEvent
from raahat.application.incident_resolution import IncidentResolutionService
from raahat.application.incident_resolution.matcher import extract_coordinates
from raahat.application.location import (
    LocationObservation,
    PostGISGazetteerResolver,
)
from raahat.application.resources import ResourceService
from raahat.application.triage import IncidentTriageService
from raahat.domain.evidence.extractor import StructuredEvidenceExtractor
from raahat.domain.evidence.repository import (
    EvidenceRepository,
    InMemoryEvidenceRepository,
)
from raahat.domain.incidents.repository import (
    IncidentRepository,
    InMemoryIncidentRepository,
)
from raahat.domain.operations.operation import Assignment, Resource
from raahat.domain.reports.report import Report
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import (
    PriorityLevel,
    ProcessingStatus,
    ResourceStatus,
    SourceType,
)
from raahat.domain.triage.assessment import PriorityAssessment
from raahat.infrastructure.database.models.incident import (
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.repositories.assignment import (
    PostgresAssignmentRepository,
)
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    InMemoryAuditRepository,
    PostgresAuditRepository,
)
from raahat.infrastructure.database.repositories.evidence import (
    PostgresEvidenceRepository,
)
from raahat.infrastructure.database.repositories.landmark import (
    PostgresLandmarkRepository,
)
from raahat.infrastructure.database.repositories.resource import (
    PostgresResourceRepository,
)
from raahat.infrastructure.speech import (
    AudioInput,
    SpeechRecognizer,
    Transcript,
    WhisperRecognizer,
)

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_DISPATCHER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@dataclass(frozen=True)
class WorkflowResult:
    """Consolidated outcome of the automated audio triage and dispatch recommendation pipeline."""

    report_id: uuid.UUID
    incident_id: uuid.UUID
    disaster_id: uuid.UUID
    transcript: str
    confidence: float
    has_speech: bool
    priority: PriorityLevel
    priority_reasons: list[str]
    is_new_incident: bool
    proposed_resource_id: Optional[uuid.UUID] = None
    proposed_resource_name: Optional[str] = None
    location_label: Optional[str] = None
    coordinates: Optional[PointCoordinates] = None
    uncertainty_radius_m: Optional[float] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary suitable for JSON serialization."""
        return {
            "report_id": str(self.report_id),
            "incident_id": str(self.incident_id),
            "disaster_id": str(self.disaster_id),
            "transcript": self.transcript,
            "confidence": self.confidence,
            "has_speech": self.has_speech,
            "priority": self.priority.value,
            "priority_reasons": list(self.priority_reasons),
            "is_new_incident": self.is_new_incident,
            "proposed_resource_id": str(self.proposed_resource_id) if self.proposed_resource_id else None,
            "proposed_resource_name": self.proposed_resource_name,
            "location_label": self.location_label,
            "coordinates": {
                "latitude": self.coordinates.latitude,
                "longitude": self.coordinates.longitude,
            } if self.coordinates else None,
            "uncertainty_radius_m": self.uncertainty_radius_m,
            "execution_time_ms": self.execution_time_ms,
        }


def _model_to_domain_report(model: ReportModel) -> Report:
    """Helper converting ORM ReportModel to frozen domain Report aggregate."""
    raw = dict(model.raw_payload or {})
    try:
        source_type = SourceType(model.source_type)
    except ValueError:
        source_type = SourceType.WEB

    try:
        proc_status = ProcessingStatus(model.processing_status)
    except ValueError:
        proc_status = ProcessingStatus.PROCESSED

    return Report(
        id=model.id,
        disaster_id=model.disaster_id,
        source_type=source_type,
        source_event_id=model.source_event_id,
        source_identity=model.source_identity or "anonymous_voice",
        device_id=model.device_id,
        channel_reference=model.channel_reference,
        raw_payload=raw,
        received_at=model.received_at,
        client_created_at=model.client_created_at,
        language_code=model.language_code,
        processing_status=proc_status,
        idempotency_key=model.idempotency_key,
    )


_WORD_NUM_MAP: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _extract_transcript_facts(text: str) -> dict[str, Any]:
    """Extract operational distress facts from transcribed audio text into structured attributes."""
    if not text:
        return {}

    lower = text.lower()
    facts: dict[str, Any] = {}

    # 1. Medical emergency & life threat
    medical_words = ("medical", "doctor", "injury", "injured", "chot", "dawai", "ambulance", "bimar", "oxygen", "patient")
    if any(w in lower for w in medical_words):
        facts["medical_emergency"] = True

    # 2. Trapped status
    trapped_words = ("trapped", "phas", "fase", "stranded", "bachao", "stuck")
    if any(w in lower for w in trapped_words):
        facts["trapped_status"] = True

    # 3. Water level trend
    if any(w in lower for w in ("badh raha", "badh", "rising", "increasing", "flood level rising")):
        facts["water_level_trend"] = "rising"
    elif any(w in lower for w in ("ghat raha", "falling", "decreasing", "receded")):
        facts["water_level_trend"] = "falling"

    # 4. Water depth
    import re
    depth_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:feet|foot|ft)", lower)
    if depth_match:
        try:
            facts["water_depth_cm"] = float(depth_match.group(1)) * 30.48
        except (ValueError, IndexError):
            pass
    else:
        meter_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:meter|metre|m\b)", lower)
        if meter_match:
            try:
                facts["water_depth_cm"] = float(meter_match.group(1)) * 100.0
            except (ValueError, IndexError):
                pass

    # 5. Headcount / People count
    count_match = re.search(r"(\d+)\s*(?:people|log|person|persons|children|elderly|adults|headcount)", lower)
    if count_match:
        try:
            facts["people_count"] = int(count_match.group(1))
        except (ValueError, IndexError):
            pass
    else:
        for word, val in _WORD_NUM_MAP.items():
            if re.search(rf"\b{word}\s+(?:people|log|person|persons|children|elderly|adults)\b", lower):
                facts["people_count"] = val
                break

    # 6. Current floor & water entering occupied floor
    if "ground floor" in lower or "ground" in lower:
        facts["current_floor"] = "ground"
        if "water entering" in lower or "paani ghus" in lower or "flood water entered" in lower:
            facts["water_entering_occupied_floor"] = True
    elif "first floor" in lower or "1st floor" in lower:
        facts["current_floor"] = "first"

    # 7. Vulnerable occupants
    if any(w in lower for w in ("elderly", "children", "child", "baby", "pregnant", "disabled", "senior", "boodhe", "bacche")):
        facts["vulnerable_present"] = True

    return facts


class AutomatedAudioTriageWorkflow:
    """Orchestrates voice intake, perceptual extraction, deterministic triage, and dispatch proposal.

    Guarantees:
    - Perceptual sensory models (Whisper/VAD) only extract text and acoustic features.
    - Life-critical triage uses deterministic rules; 'Unknown never lowers priority'.
    - Resource assignment is strictly PROPOSED; human operator approval required for dispatch.
    - Full cryptographic SHA-256 audit log on every state mutation.
    """

    def __init__(
        self,
        session_factory: Optional[sessionmaker[Session]] = None,
        speech_recognizer: Optional[SpeechRecognizer] = None,
        vad_detector: Optional[VADDetector] = None,
        location_resolver: Optional[PostGISGazetteerResolver] = None,
        incident_service: Optional[IncidentResolutionService] = None,
        triage_service: Optional[IncidentTriageService] = None,
        resource_service: Optional[ResourceService] = None,
        dispatch_service: Optional[DispatchService] = None,
        evidence_extractor: Optional[StructuredEvidenceExtractor] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
        incident_repo: Optional[IncidentRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        broadcaster: Optional[EventBroadcaster] = None,
        system_dispatcher_id: Optional[uuid.UUID] = None,
    ) -> None:
        self.session_factory = session_factory
        self.speech_recognizer = speech_recognizer or WhisperRecognizer(allow_fallback=True)
        self.vad_detector = vad_detector or EnergyVADDetector()
        self.evidence_extractor = evidence_extractor or StructuredEvidenceExtractor()
        self.system_dispatcher_id = system_dispatcher_id or DEFAULT_SYSTEM_DISPATCHER_ID

        # Repositories
        self.incident_repo: Optional[IncidentRepository]
        if incident_repo is not None:
            self.incident_repo = incident_repo
        elif session_factory is None:
            self.incident_repo = InMemoryIncidentRepository()
        else:
            self.incident_repo = None

        if evidence_repo is not None:
            self.evidence_repo = evidence_repo
        elif session_factory is not None:
            self.evidence_repo = PostgresEvidenceRepository(session_factory)
        else:
            self.evidence_repo = InMemoryEvidenceRepository()

        if audit_repo is not None:
            self.audit_repo = audit_repo
        elif session_factory is not None:
            self.audit_repo = PostgresAuditRepository(session_factory)
        else:
            self.audit_repo = InMemoryAuditRepository()

        # Services
        self.incident_service = incident_service or (
            IncidentResolutionService(
                incident_repo=self.incident_repo,
                session_factory=session_factory,
            )
            if session_factory is not None
            else IncidentResolutionService(incident_repo=self.incident_repo)
        )
        self.triage_service = triage_service or IncidentTriageService(
            incident_repo=self.incident_repo,
            evidence_repo=self.evidence_repo,
            audit_repo=self.audit_repo,
            session_factory=session_factory,
        )

        if resource_service is not None:
            self.resource_service = resource_service
        elif session_factory is not None:
            self.resource_service = ResourceService(
                resource_repo=PostgresResourceRepository(session_factory),
                audit_repo=self.audit_repo,
                session_factory=session_factory,
            )
        else:
            self.resource_service = ResourceService(audit_repo=self.audit_repo)

        if dispatch_service is not None:
            self.dispatch_service = dispatch_service
        elif session_factory is not None:
            self.dispatch_service = DispatchService(
                assignment_repo=PostgresAssignmentRepository(session_factory),
                audit_repo=self.audit_repo,
                session_factory=session_factory,
            )
        else:
            self.dispatch_service = DispatchService(audit_repo=self.audit_repo)

        self.location_resolver: Optional[PostGISGazetteerResolver]
        if location_resolver is not None:
            self.location_resolver = location_resolver
        elif session_factory is not None:
            self.location_resolver = PostGISGazetteerResolver(
                landmark_repo=PostgresLandmarkRepository(session_factory)
            )
        else:
            self.location_resolver = None

        self.broadcaster = broadcaster

    async def run(
        self,
        audio_input: AudioInput,
        disaster_id: uuid.UUID,
        caller_info: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """Execute the complete pipeline on incoming raw distress audio."""
        start_time = time.perf_counter()

        # ------------------------------------------------------------------
        # 1. Perception: VAD & Speech Transcription
        # ------------------------------------------------------------------
        has_speech = self.vad_detector.detect_speech(audio_input)
        language_hint = caller_info.get("language_hint") if caller_info else None
        transcript = await self.speech_recognizer.transcribe(
            audio_input,
            language_hint=language_hint,
        )
        transcript_text = transcript.text or ""

        # ------------------------------------------------------------------
        # 2. Location & Landmark Disambiguation
        # ------------------------------------------------------------------
        direct_coords: Optional[PointCoordinates] = None
        if caller_info:
            lat = caller_info.get("latitude")
            lon = caller_info.get("longitude")
            if lat is not None and lon is not None:
                try:
                    direct_coords = PointCoordinates(latitude=float(lat), longitude=float(lon))
                except (ValueError, TypeError):
                    direct_coords = None

        target_coords, location_label, uncertainty_radius_m = await self._resolve_location(
            raw_text=transcript_text,
            direct_coords=direct_coords,
        )

        # ------------------------------------------------------------------
        # 3. Report Ingestion & Persistence
        # ------------------------------------------------------------------
        report = self._persist_report(
            disaster_id=disaster_id,
            transcript=transcript,
            has_speech=has_speech,
            target_coords=target_coords,
            location_label=location_label,
            uncertainty_radius_m=uncertainty_radius_m,
            caller_info=caller_info,
        )

        # ------------------------------------------------------------------
        # 4. Structured Evidence Fact Extraction
        # ------------------------------------------------------------------
        evidence_items = self.evidence_extractor.extract(report)
        if evidence_items:
            try:
                self.evidence_repo.save_all(evidence_items)
            except Exception as e:
                logger.warning("Failed saving evidence items for report %s: %s", report.id, e)

        # ------------------------------------------------------------------
        # 5. Canonical Incident Match / Creation
        # ------------------------------------------------------------------
        resolution_result = self.incident_service.resolve_report(
            report=report,
            evidence_items=evidence_items,
        )
        incident_id = resolution_result.incident_id
        is_new_incident = resolution_result.is_new_incident

        # Ensure spatial hypothesis is recorded on the incident
        if target_coords and self.session_factory is not None:
            self._update_incident_location(
                incident_id=incident_id,
                target_coords=target_coords,
                location_label=location_label,
                uncertainty_radius_m=uncertainty_radius_m,
            )

        # ------------------------------------------------------------------
        # 6. Deterministic Safety Policy Triage (P0-P3)
        # ------------------------------------------------------------------
        incident, assessment = self.triage_service.triage_incident(
            incident_id=incident_id,
            actor_id=self.system_dispatcher_id,
        )

        # ------------------------------------------------------------------
        # 7. Nearest Rescue Resource Recommendation (Proposed)
        # ------------------------------------------------------------------
        proposed_res, assignment = self._propose_rescue_unit(
            disaster_id=disaster_id,
            incident_id=incident_id,
            assessment=assessment,
            target_coords=target_coords,
        )

        # ------------------------------------------------------------------
        # 8. Real-Time SSE Event Broadcast
        # ------------------------------------------------------------------
        self._broadcast_events(
            disaster_id=disaster_id,
            report=report,
            transcript_text=transcript_text,
            has_speech=has_speech,
            incident_id=incident_id,
            is_new_incident=is_new_incident,
            incident_status=incident.status.value,
            assessment=assessment,
            target_coords=target_coords,
            proposed_res=proposed_res,
            assignment=assignment,
        )

        execution_time_ms = (time.perf_counter() - start_time) * 1000.0

        return WorkflowResult(
            report_id=report.id,
            incident_id=incident_id,
            disaster_id=disaster_id,
            transcript=transcript_text,
            confidence=transcript.confidence,
            has_speech=has_speech,
            priority=assessment.priority,
            priority_reasons=list(assessment.reasons),
            is_new_incident=is_new_incident,
            proposed_resource_id=proposed_res.id if proposed_res else None,
            proposed_resource_name=proposed_res.name if proposed_res else None,
            location_label=location_label,
            coordinates=target_coords,
            uncertainty_radius_m=uncertainty_radius_m,
            execution_time_ms=execution_time_ms,
        )

    async def run_for_report(self, report_id: uuid.UUID) -> WorkflowResult:
        """Run downstream triage and dispatch orchestration for an existing persisted report."""
        if self.session_factory is None:
            raise ValueError("run_for_report requires a database session_factory")

        start_time = time.perf_counter()

        with self.session_factory() as session:
            report_m = session.get(ReportModel, report_id)
            if report_m is None:
                raise ValueError(f"Report ticket '{report_id}' not found")

            disaster_id = report_m.disaster_id
            raw_payload = dict(report_m.raw_payload or {})

            # 1. Transcribe audio if still pending
            transcript_text = raw_payload.get("transcript") or raw_payload.get("text") or ""
            confidence = float(raw_payload.get("transcript_confidence", 0.95))
            has_speech = bool(raw_payload.get("has_speech", True))

            if report_m.processing_status == "pending" and "audio" in raw_payload:
                audio_meta = raw_payload["audio"]
                audio_bytes: bytes = b""
                if isinstance(audio_meta, dict):
                    audio_path_str = audio_meta.get("path")
                    if audio_path_str and Path(audio_path_str).exists():
                        audio_bytes = Path(audio_path_str).read_bytes()
                    elif "audio_bytes" in audio_meta:
                        raw_bytes = audio_meta["audio_bytes"]
                        audio_bytes = (
                            raw_bytes.encode("utf-8") if isinstance(raw_bytes, str) else raw_bytes
                        )

                if audio_bytes:
                    audio_input = AudioInput(
                        audio_bytes=audio_bytes,
                        sample_rate=audio_meta.get("sample_rate", 16000),
                    )
                    has_speech = self.vad_detector.detect_speech(audio_input)
                    transcript = await self.speech_recognizer.transcribe(
                        audio_input, language_hint=report_m.language_code
                    )
                    transcript_text = transcript.text
                    confidence = transcript.confidence
                    raw_payload["transcript"] = transcript_text
                    raw_payload["transcript_confidence"] = confidence
                    raw_payload["has_speech"] = has_speech
                    raw_payload["text"] = transcript_text or raw_payload.get("situation_description", "Voice report")

                report_m.raw_payload = raw_payload
                report_m.processing_status = "extracted"
                session.commit()
                session.refresh(report_m)

            if "parsed" not in raw_payload or not raw_payload["parsed"]:
                extracted = _extract_transcript_facts(transcript_text)
                if extracted:
                    raw_payload["parsed"] = extracted
                    report_m.raw_payload = raw_payload
                    session.commit()
                    session.refresh(report_m)

            report = _model_to_domain_report(report_m)

        # 2. Location disambiguation
        direct_coords = extract_coordinates(report)
        target_coords, location_label, uncertainty_radius_m = await self._resolve_location(
            raw_text=transcript_text,
            direct_coords=direct_coords,
        )

        # 3. Structured Evidence extraction
        evidence_items = self.evidence_extractor.extract(report)
        if evidence_items:
            try:
                self.evidence_repo.save_all(evidence_items)
            except Exception as e:
                logger.warning("Failed saving evidence items for report %s: %s", report.id, e)

        # 4. Check if report already linked to an incident
        incident_id: Optional[uuid.UUID] = None
        is_new_incident = False

        with self.session_factory() as session:
            existing_link = session.scalars(
                select(IncidentReportModel).where(IncidentReportModel.report_id == report_id)
            ).first()
            if existing_link is not None:
                incident_id = existing_link.incident_id

        if incident_id is None:
            resolution_result = self.incident_service.resolve_report(
                report=report,
                evidence_items=evidence_items,
            )
            incident_id = resolution_result.incident_id
            is_new_incident = resolution_result.is_new_incident

        # Update location on incident
        if target_coords:
            self._update_incident_location(
                incident_id=incident_id,
                target_coords=target_coords,
                location_label=location_label,
                uncertainty_radius_m=uncertainty_radius_m,
            )

        # 5. Deterministic Safety Policy Triage
        incident, assessment = self.triage_service.triage_incident(
            incident_id=incident_id,
            actor_id=self.system_dispatcher_id,
        )

        # 6. Nearest Rescue Resource Recommendation
        proposed_res, assignment = self._propose_rescue_unit(
            disaster_id=disaster_id,
            incident_id=incident_id,
            assessment=assessment,
            target_coords=target_coords,
        )

        # 7. SSE Broadcast
        self._broadcast_events(
            disaster_id=disaster_id,
            report=report,
            transcript_text=transcript_text,
            has_speech=has_speech,
            incident_id=incident_id,
            is_new_incident=is_new_incident,
            incident_status=incident.status.value,
            assessment=assessment,
            target_coords=target_coords,
            proposed_res=proposed_res,
            assignment=assignment,
        )

        execution_time_ms = (time.perf_counter() - start_time) * 1000.0

        return WorkflowResult(
            report_id=report.id,
            incident_id=incident_id,
            disaster_id=disaster_id,
            transcript=transcript_text,
            confidence=confidence,
            has_speech=has_speech,
            priority=assessment.priority,
            priority_reasons=list(assessment.reasons),
            is_new_incident=is_new_incident,
            proposed_resource_id=proposed_res.id if proposed_res else None,
            proposed_resource_name=proposed_res.name if proposed_res else None,
            location_label=location_label,
            coordinates=target_coords,
            uncertainty_radius_m=uncertainty_radius_m,
            execution_time_ms=execution_time_ms,
        )

    # ----------------------------------------------------------------------
    # Internal Pipeline Steps
    # ----------------------------------------------------------------------

    async def _resolve_location(
        self,
        raw_text: str,
        direct_coords: Optional[PointCoordinates],
    ) -> tuple[Optional[PointCoordinates], Optional[str], Optional[float]]:
        """Resolve spatial coordinates, label, and uncertainty bounds."""
        target_coords = direct_coords
        location_label: Optional[str] = None
        uncertainty_radius_m: Optional[float] = None

        if self.location_resolver is not None:
            try:
                loc_res = await self.location_resolver.resolve(
                    LocationObservation(
                        incident_id=uuid.uuid4(),
                        raw_text=raw_text,
                        coordinates=direct_coords,
                    )
                )
                if loc_res.hypotheses:
                    best_hyp = loc_res.hypotheses[0]
                    target_coords = best_hyp.coordinates
                    location_label = best_hyp.candidate_label
                    uncertainty_radius_m = best_hyp.uncertainty_radius_m or loc_res.uncertainty_radius_m
                elif direct_coords:
                    uncertainty_radius_m = loc_res.uncertainty_radius_m
            except Exception as e:
                logger.warning("Gazetteer location resolution error: %s", e)
                target_coords = direct_coords

        return target_coords, location_label, uncertainty_radius_m

    def _persist_report(
        self,
        disaster_id: uuid.UUID,
        transcript: Transcript,
        has_speech: bool,
        target_coords: Optional[PointCoordinates],
        location_label: Optional[str],
        uncertainty_radius_m: Optional[float],
        caller_info: Optional[dict[str, Any]],
    ) -> Report:
        """Persist report record into database or in-memory domain aggregate."""
        report_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        source_identity = (
            (caller_info.get("caller_phone") or caller_info.get("source_identity") or "anonymous_voice")
            if caller_info
            else "anonymous_voice"
        )
        idempotency_key = (
            (caller_info.get("idempotency_key") or f"voice_{report_id.hex}")
            if caller_info
            else f"voice_{report_id.hex}"
        )

        clean_transcript_text = (transcript.text or "").replace("\x00", "")
        extracted_facts = _extract_transcript_facts(clean_transcript_text)
        raw_payload: dict[str, Any] = {
            "text": clean_transcript_text or "Distress voice note",
            "transcript": clean_transcript_text,
            "transcript_confidence": transcript.confidence,
            "transcript_language": transcript.language,
            "has_speech": has_speech,
            "parsed": extracted_facts,
        }
        if target_coords:
            raw_payload["location"] = {
                "latitude": target_coords.latitude,
                "longitude": target_coords.longitude,
            }
        if location_label:
            raw_payload["location_label"] = location_label
        if uncertainty_radius_m is not None:
            raw_payload["uncertainty_radius_m"] = uncertainty_radius_m
        if caller_info:
            for k, v in caller_info.items():
                if k not in raw_payload and k not in ("latitude", "longitude"):
                    raw_payload[k] = v

        if self.session_factory is not None:
            with self.session_factory() as session:
                model = ReportModel(
                    id=report_id,
                    disaster_id=disaster_id,
                    source_type="citizen_web_voice",
                    source_identity=source_identity,
                    raw_payload=raw_payload,
                    processing_status="extracted",
                    idempotency_key=idempotency_key,
                    language_code=transcript.language or "und",
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return _model_to_domain_report(model)

        return Report(
            id=report_id,
            disaster_id=disaster_id,
            source_type=SourceType.WEB,
            source_identity=source_identity,
            raw_payload=raw_payload,
            processing_status=ProcessingStatus.PROCESSED,
            idempotency_key=idempotency_key,
            received_at=now,
        )

    def _update_incident_location(
        self,
        incident_id: uuid.UUID,
        target_coords: PointCoordinates,
        location_label: Optional[str],
        uncertainty_radius_m: Optional[float],
    ) -> None:
        """Update or insert LocationHypothesisModel on incident record."""
        if self.session_factory is None:
            return

        with self.session_factory() as session:
            hyp = session.scalars(
                select(LocationHypothesisModel).where(
                    LocationHypothesisModel.incident_id == incident_id
                )
            ).first()
            if hyp:
                if location_label:
                    hyp.candidate_label = location_label
                if uncertainty_radius_m is not None:
                    hyp.uncertainty_radius_m = uncertainty_radius_m
                session.commit()
            else:
                new_hyp = LocationHypothesisModel(
                    id=uuid.uuid4(),
                    incident_id=incident_id,
                    location=f"SRID=4326;{target_coords.to_wkt()}",
                    candidate_label=location_label or "voice_report_pin",
                    probability=None,
                    uncertainty_radius_m=uncertainty_radius_m,
                    verification_status="unverified",
                )
                session.add(new_hyp)
                session.commit()

    def _propose_rescue_unit(
        self,
        disaster_id: uuid.UUID,
        incident_id: uuid.UUID,
        assessment: PriorityAssessment,
        target_coords: Optional[PointCoordinates],
    ) -> tuple[Optional[Resource], Optional[Assignment]]:
        """Find the nearest available resource and propose assignment with human-in-the-loop."""
        proposed_res: Optional[Resource] = None
        assignment: Optional[Assignment] = None

        if self.resource_service is not None:
            if target_coords is not None:
                nearby = self.resource_service.find_nearby_resources(
                    disaster_id=disaster_id,
                    coordinates=target_coords,
                    radius_meters=35000.0,
                    status=ResourceStatus.AVAILABLE,
                    limit=1,
                )
                if nearby:
                    proposed_res = nearby[0].resource

            if proposed_res is None:
                available = self.resource_service.list_resources(
                    disaster_id=disaster_id,
                    status=ResourceStatus.AVAILABLE,
                )
                if available:
                    proposed_res = available[0]

        if proposed_res is not None and self.dispatch_service is not None:
            notes = f"Proposed assignment for {assessment.priority.value.upper()} incident based on proximity"
            try:
                assignment, _ = self.dispatch_service.propose_assignment(
                    incident_id=incident_id,
                    resource_id=proposed_res.id,
                    dispatcher_id=self.system_dispatcher_id,
                    notes=notes,
                )
            except Exception as e:
                logger.warning("Failed proposing rescue assignment: %s", e)

        return proposed_res, assignment

    def _broadcast_events(
        self,
        disaster_id: uuid.UUID,
        report: Report,
        transcript_text: str,
        has_speech: bool,
        incident_id: uuid.UUID,
        is_new_incident: bool,
        incident_status: str,
        assessment: PriorityAssessment,
        target_coords: Optional[PointCoordinates],
        proposed_res: Optional[Resource],
        assignment: Optional[Assignment],
    ) -> None:
        """Publish real-time operational updates to connected dispatcher consoles."""
        if self.broadcaster is None:
            return

        # 1. Report live event
        self.broadcaster.publish(
            LiveEvent(
                event_type="report.created",
                aggregate_type="report",
                aggregate_id=report.id,
                disaster_id=disaster_id,
                payload={
                    "report_id": str(report.id),
                    "source_type": report.source_type.value
                    if hasattr(report.source_type, "value")
                    else str(report.source_type),
                    "text": transcript_text,
                    "has_speech": has_speech,
                    "status": "extracted",
                    "received_at": report.received_at.isoformat(),
                },
            )
        )

        # 2. Incident created event (if newly created)
        if is_new_incident:
            self.broadcaster.publish(
                LiveEvent(
                    event_type="incident.created",
                    aggregate_type="incident",
                    aggregate_id=incident_id,
                    disaster_id=disaster_id,
                    payload={
                        "incident_id": str(incident_id),
                        "disaster_id": str(disaster_id),
                        "priority": assessment.priority.value,
                        "status": incident_status,
                        "coordinates": {
                            "latitude": target_coords.latitude,
                            "longitude": target_coords.longitude,
                        }
                        if target_coords
                        else None,
                    },
                )
            )

        # 3. Incident triaged event
        self.broadcaster.publish(
            LiveEvent(
                event_type="incident.triaged",
                aggregate_type="incident",
                aggregate_id=incident_id,
                disaster_id=disaster_id,
                payload={
                    "incident_id": str(incident_id),
                    "disaster_id": str(disaster_id),
                    "priority": assessment.priority.value,
                    "reasons": list(assessment.reasons),
                    "unknown_fields": list(assessment.unknown_fields),
                    "requires_human_review": assessment.requires_human_review,
                },
            )
        )

        # 4. Rescue unit proposed event
        if assignment is not None and proposed_res is not None:
            self.broadcaster.publish(
                LiveEvent(
                    event_type="operation.proposed",
                    aggregate_type="assignment",
                    aggregate_id=assignment.id,
                    disaster_id=disaster_id,
                    payload={
                        "assignment_id": str(assignment.id),
                        "incident_id": str(incident_id),
                        "resource_id": str(proposed_res.id),
                        "resource_name": proposed_res.name,
                        "status": "proposed",
                        "assigned_by": str(self.system_dispatcher_id),
                    },
                )
            )
