"""Report analysis pipeline.

A report moves through up to three stages. Each stage records a processing run
naming the provider that did the work, and each produces evidence that points
back at the words it came from.

1. **Transcription** (audio reports only, worker): speech provider → original
   text and language.
2. **Initial analysis** (in the request for operator-entered text; in the
   worker for channel reports): language identification, rule-based
   extraction, landmark candidates, duplicate candidates, incident creation,
   triage. Deterministic and local, so it works with no provider configured.
3. **Enrichment** (worker, only when a text model is configured): translation
   to English and model extraction, after which triage is re-run.

The report's original text is written once and never modified.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.ai import enrichment, rules
from raahat.application.ai.language import identify_language
from raahat.application.ai.registry import Providers
from raahat.application.incident_resolution import (
    ConservativeIncidentMatcher,
    ConservativeIncidentResolver,
    IncidentResolutionService,
)
from raahat.application.location import service as locations
from raahat.application.location.candidates import search_landmarks
from raahat.application.triage import IncidentTriageService
from raahat.config import Settings
from raahat.domain.evidence.evidence import EvidenceItem, EvidenceSpan
from raahat.domain.evidence.extractor import StructuredEvidenceExtractor
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import (
    LocationSource,
    ProcessingStatus,
    SourceType,
    VerificationStatus,
)
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.evidence import EvidenceItemModel
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.models.system import ProcessingRunModel
from raahat.infrastructure.database.repositories.audit import (
    PostgresAuditRepository,
    append_audit,
)
from raahat.infrastructure.database.repositories.evidence import (
    PostgresEvidenceRepository,
    evidence_item_to_model,
)
from raahat.infrastructure.providers.base import ProviderError, ProviderNotConfigured

logger = logging.getLogger(__name__)

TEXT_KEYS = ("situation_description", "text", "message", "transcript", "notes", "body")
MAX_LANDMARK_CANDIDATES = 5
OPERATION_SEARCH_RADIUS_M = 75_000.0


@dataclass
class AnalysisOutcome:
    report_id: uuid.UUID
    incident_id: Optional[uuid.UUID]
    is_new_incident: bool
    duplicate_candidates: int = 0
    location_candidates: int = 0
    notes: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def text_from_payload(payload: dict[str, Any]) -> Optional[str]:
    for key in TEXT_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def record_run(
    session: Session,
    *,
    report_id: uuid.UUID,
    stage: str,
    provider: str,
    status: str,
    model: Optional[str] = None,
    duration_ms: Optional[float] = None,
    confidence: Optional[float] = None,
    error: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    session.add(
        ProcessingRunModel(
            id=uuid.uuid4(),
            report_id=report_id,
            stage=stage,
            provider=provider,
            model=model,
            status=status,
            duration_ms=duration_ms,
            confidence=confidence,
            error=(error or None) and error[:1000],
            details=details or {},
        )
    )


def _to_domain(report: ReportModel) -> Report:
    return Report(
        id=report.id,
        disaster_id=report.disaster_id,
        source_type=SourceType(report.source_type),
        source_event_id=report.source_event_id,
        source_identity=report.source_identity,
        device_id=report.device_id,
        channel_reference=report.channel_reference,
        raw_payload=dict(report.raw_payload or {}),
        received_at=report.received_at,
        client_created_at=report.client_created_at,
        language_code=report.language_code,
        processing_status=ProcessingStatus.PENDING,
        idempotency_key=report.idempotency_key,
    )


def _evidence(
    report: ReportModel,
    *,
    attribute: str,
    value: Any,
    quote: Optional[str],
    extractor: str,
    model: Optional[str] = None,
    note: Optional[str] = None,
) -> EvidenceItem:
    reference: dict[str, Any] = {"extractor": extractor}
    if model:
        reference["model"] = model
    if note:
        reference["note"] = note
    return EvidenceItem(
        report_id=report.id,
        subject_type="incident",
        attribute=attribute,
        value=value,
        # No calibrated confidence exists for either extractor; left unknown.
        confidence=None,
        verification_status=VerificationStatus.UNVERIFIED,
        observed_at=report.client_created_at or report.received_at,
        spans=(EvidenceSpan(text=quote, reference=reference),),
    )


def _existing_evidence_keys(session: Session, report_id: uuid.UUID) -> set[tuple[str, str]]:
    rows = session.execute(
        select(EvidenceItemModel.attribute, EvidenceItemModel.value).where(
            EvidenceItemModel.report_id == report_id
        )
    ).all()
    return {(attribute, repr(value)) for attribute, value in rows}


def _incident_for_report(session: Session, report_id: uuid.UUID) -> Optional[IncidentModel]:
    link = session.execute(
        select(IncidentReportModel)
        .where(IncidentReportModel.report_id == report_id)
        .order_by(IncidentReportModel.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    return session.get(IncidentModel, link.incident_id) if link else None


def _operation_focus(session: Session, disaster_id: uuid.UUID) -> Optional[tuple[float, float]]:
    row = session.execute(
        text(
            "SELECT ST_Y(map_center::geometry) AS lat, ST_X(map_center::geometry) AS lon "
            "FROM disasters WHERE id = :id AND map_center IS NOT NULL"
        ),
        {"id": disaster_id},
    ).first()
    return (float(row.lat), float(row.lon)) if row else None


class ReportPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        providers: Providers,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._settings = settings
        self._providers = providers
        # (integration key, succeeded, detail, latency ms) for each real
        # provider call, drained by the caller into integration status.
        self.provider_results: list[tuple[str, bool, str, Optional[float]]] = []
        self._structured = StructuredEvidenceExtractor()
        self._resolution = IncidentResolutionService(
            matcher=ConservativeIncidentMatcher(),
            resolver=ConservativeIncidentResolver(
                auto_link_threshold=settings.dedup_auto_link_threshold,
                review_threshold=settings.dedup_review_threshold,
            ),
            session_factory=session_factory,
        )
        self._triage = IncidentTriageService(
            evidence_repo=PostgresEvidenceRepository(session_factory),
            audit_repo=PostgresAuditRepository(session_factory),
            session_factory=session_factory,
        )

    @property
    def enrichment_available(self) -> bool:
        model = self._providers.text_model
        return model is not None and model.configured

    # ------------------------------------------------------------------ stage 1
    def transcribe(self, session: Session, report: ReportModel, audio: bytes) -> bool:
        """Transcribe audio into the report's original text. Returns True on success."""
        speech = self._providers.speech
        try:
            result = speech.transcribe(audio, language_hint=report.language_code)
        except ProviderNotConfigured as exc:
            record_run(
                session, report_id=report.id, stage="transcription", provider=speech.name,
                model=speech.model, status="not_configured", error=str(exc),
            )
            report.processing_error = (
                "Audio was not transcribed: the speech provider is not configured. "
                "Listen to the recording."
            )
            return False
        except ProviderError as exc:
            record_run(
                session, report_id=report.id, stage="transcription", provider=speech.name,
                model=speech.model, status="failed", error=str(exc),
            )
            report.processing_error = f"Audio transcription failed ({exc}). Listen to the recording."
            self.provider_results.append(("speech", False, str(exc), None))
            return False

        record_run(
            session, report_id=report.id, stage="transcription", provider=result.provider,
            model=result.model, status="succeeded", duration_ms=result.duration_ms,
            confidence=result.confidence,
            details={"characters": len(result.text), "language": result.language},
        )
        self.provider_results.append(
            ("speech", True, f"Transcribed {len(result.text)} characters", result.duration_ms)
        )
        if not result.text:
            report.processing_error = "The recording contained no recognisable speech."
            return False
        report.original_text = result.text
        if result.language:
            report.original_language = result.language.split("-")[0].lower()
            report.language_source = result.provider
            report.language_confidence = None
        report.processing_error = None
        return True

    # ------------------------------------------------------------------ stage 2
    def analyse(
        self, session: Session, report: ReportModel, *, actor_id: Optional[uuid.UUID] = None
    ) -> AnalysisOutcome:
        """Initial deterministic analysis. Idempotent: a report already attached
        to an incident is not analysed again."""
        existing = _incident_for_report(session, report.id)
        if existing is not None:
            return AnalysisOutcome(report.id, existing.id, False, notes=["already analysed"])

        payload = dict(report.raw_payload or {})
        if report.original_text is None:
            report.original_text = text_from_payload(payload)
        body = report.original_text or ""

        if body and not report.original_language:
            guess = identify_language(body)
            report.original_language = guess.language
            report.language_source = "script_heuristic"
            record_run(
                session, report_id=report.id, stage="language_id", provider="script_heuristic",
                status="succeeded",
                details={
                    "language": guess.language,
                    "certain": guess.certain,
                    "basis": guess.basis,
                    "alternatives": list(guess.alternatives),
                },
            )

        domain_report = _to_domain(report)
        evidence: list[EvidenceItem] = []
        # Fields the caller or operator filled in directly (count, needs, ...).
        for item in self._structured.extract(domain_report):
            span = item.spans[0] if item.spans else EvidenceSpan(text=None, reference={})
            reference = {**span.reference, "extractor": "submitted_field"}
            evidence.append(
                item.model_copy(update={"spans": (span.model_copy(update={"reference": reference}),)})
            )
        structured_keys = {(e.attribute, repr(e.value)) for e in evidence}

        extraction = rules.extract(body)
        for finding in extraction.findings:
            if (finding.attribute, repr(finding.value)) in structured_keys:
                continue
            evidence.append(
                _evidence(
                    report, attribute=finding.attribute, value=finding.value,
                    quote=finding.matched_text, extractor=rules.EXTRACTOR_NAME, note=finding.note,
                )
            )
        if extraction.category:
            evidence.append(
                _evidence(
                    report, attribute="category", value=extraction.category,
                    quote=extraction.category_matched_text, extractor=rules.EXTRACTOR_NAME,
                )
            )
        if body:
            record_run(
                session, report_id=report.id, stage="extraction", provider=rules.EXTRACTOR_NAME,
                model=rules.EXTRACTOR_VERSION, status="succeeded",
                details={
                    "findings": len(extraction.findings),
                    "location_mentions": len(extraction.location_mentions),
                },
            )

        for item in evidence:
            session.add(evidence_item_to_model(item))
        session.flush()

        resolution = self._resolution._resolve_with_session(domain_report, evidence, session)
        incident = session.get(IncidentModel, resolution.incident_id)
        assert incident is not None
        session.refresh(incident)
        outcome = AnalysisOutcome(report.id, incident.id, resolution.is_new_incident)

        if resolution.is_new_incident:
            incident.created_by = report.created_by
            incident.source_channel = report.source_type
            location_text = payload.get("location_text")
            if isinstance(location_text, str) and location_text.strip():
                incident.location_description = location_text.strip()
            elif extraction.location_mentions:
                incident.location_description = "; ".join(
                    m.matched_text for m in extraction.location_mentions[:3]
                )
            if extraction.category:
                incident.category = extraction.category

            phrases: list[tuple[str, Optional[str]]] = [
                (m.phrase, m.relation) for m in extraction.location_mentions
            ]
            if isinstance(location_text, str) and location_text.strip():
                phrases.insert(0, (location_text.strip(), None))
            outcome.location_candidates = self._add_landmark_candidates(
                session, incident, report, phrases, extractor=rules.EXTRACTOR_NAME
            )
            locations.refresh_incident_location(session, incident)

            links = session.execute(
                select(IncidentLinkModel).where(
                    IncidentLinkModel.incident_a_id == incident.id,
                    IncidentLinkModel.status == "pending_review",
                )
            ).scalars().all()
            outcome.duplicate_candidates = len(links)

        self._triage._triage_with_session(incident.id, session, actor_id=None)
        session.refresh(incident)

        append_audit(
            session,
            action="report.received",
            actor_id=actor_id,
            entity_type="report",
            entity_id=report.id,
            disaster_id=report.disaster_id,
            incident_id=incident.id,
            payload={"channel": report.source_type, "language": report.original_language},
        )
        if resolution.is_new_incident:
            append_audit(
                session,
                action="incident.created",
                actor_id=actor_id,
                entity_type="incident",
                entity_id=incident.id,
                disaster_id=incident.disaster_id,
                payload={
                    "reference": incident.reference,
                    "report_id": str(report.id),
                    "priority": incident.operational_priority,
                    "category": incident.category,
                    "location_status": incident.location_status,
                },
            )
            if outcome.duplicate_candidates:
                append_audit(
                    session,
                    action="incident.duplicate_candidates_found",
                    actor_id=None,
                    entity_type="incident",
                    entity_id=incident.id,
                    disaster_id=incident.disaster_id,
                    payload={
                        "candidates": outcome.duplicate_candidates,
                        "rationale": resolution.decision.rationale,
                    },
                )
        else:
            append_audit(
                session,
                action="incident.report_attached",
                actor_id=actor_id,
                entity_type="incident",
                entity_id=incident.id,
                disaster_id=incident.disaster_id,
                payload={"report_id": str(report.id), "rationale": resolution.decision.rationale},
            )
        return outcome

    def _add_landmark_candidates(
        self,
        session: Session,
        incident: IncidentModel,
        report: ReportModel,
        phrases: list[tuple[str, Optional[str]]],
        *,
        extractor: str,
    ) -> int:
        """Search the gazetteer for each phrase and store the best matches as candidates."""
        if not phrases:
            return 0
        focus = _operation_focus(session, incident.disaster_id)
        existing = {
            str(v.source_detail.get("landmark_id"))
            for v in locations.list_hypotheses(session, incident.id)
            if v.source == LocationSource.LANDMARK.value
        }
        added = 0
        searched: list[dict[str, Any]] = []
        for phrase, relation in phrases[:6]:
            matches = search_landmarks(
                session, phrase, focus=focus, radius_m=OPERATION_SEARCH_RADIUS_M,
                limit=MAX_LANDMARK_CANDIDATES,
            )
            searched.append({"phrase": phrase, "matches": len(matches)})
            for match in matches:
                if str(match.landmark_id) in existing or added >= MAX_LANDMARK_CANDIDATES:
                    continue
                existing.add(str(match.landmark_id))
                locations.add_hypothesis(
                    session,
                    incident_id=incident.id,
                    latitude=match.latitude,
                    longitude=match.longitude,
                    source=LocationSource.LANDMARK,
                    label=(f"{relation.replace('_', ' ')} " if relation and relation != "at" else "")
                    + match.name,
                    # Name similarity (0-1). A ranking signal, not a probability.
                    score=match.similarity,
                    uncertainty_radius_m=locations.ASSUMED_LANDMARK_RADIUS_M.get(
                        relation or "", locations.DEFAULT_LANDMARK_RADIUS_M
                    ),
                    report_id=report.id,
                    source_detail={
                        "landmark_id": str(match.landmark_id),
                        "landmark_name": match.name,
                        "landmark_kind": match.kind,
                        "landmark_source": match.source,
                        "matched_phrase": phrase,
                        "relation": relation,
                        "name_similarity": match.similarity,
                        "extractor": extractor,
                        "radius_basis": "assumed",
                    },
                )
                added += 1
        record_run(
            session, report_id=report.id, stage="location", provider="landmark_gazetteer",
            status="succeeded", details={"searched": searched, "candidates_added": added},
        )
        return added

    # ------------------------------------------------------------------ stage 3
    def enrich(self, session: Session, report: ReportModel) -> bool:
        """Translate and run model extraction. Returns True if anything was added."""
        client = self._providers.text_model
        body = report.original_text or ""
        if client is None or not body:
            return False
        incident = _incident_for_report(session, report.id)
        changed = False

        needs_translation = report.original_language not in (None, "en") and not report.translated_text
        if needs_translation:
            try:
                translation = enrichment.translate_to_english(
                    client, text=body, source_language=report.original_language
                )
            except ProviderNotConfigured as exc:
                record_run(session, report_id=report.id, stage="translation", provider=client.name,
                           model=client.model, status="not_configured", error=str(exc))
                return False
            except ProviderError as exc:
                record_run(session, report_id=report.id, stage="translation", provider=client.name,
                           model=client.model, status="failed", error=str(exc))
                self.provider_results.append(("text_model", False, str(exc), None))
            else:
                report.translated_text = translation.text
                report.translation_provider = f"{translation.provider}:{translation.model}"
                record_run(
                    session, report_id=report.id, stage="translation", provider=translation.provider,
                    model=translation.model, status="succeeded", duration_ms=translation.duration_ms,
                    details={"reported_source_language": translation.source_language},
                )
                changed = True

        try:
            extraction = enrichment.extract_with_model(
                client, text=body, translated_text=report.translated_text
            )
        except ProviderNotConfigured as exc:
            record_run(session, report_id=report.id, stage="extraction", provider=client.name,
                       model=client.model, status="not_configured", error=str(exc))
            return changed
        except ProviderError as exc:
            record_run(session, report_id=report.id, stage="extraction", provider=client.name,
                       model=client.model, status="failed", error=str(exc))
            self.provider_results.append(("text_model", False, str(exc), None))
            return changed
        self.provider_results.append(
            ("text_model", True, f"Extraction by {extraction.model}", extraction.duration_ms)
        )

        known = _existing_evidence_keys(session, report.id)
        added = 0
        for finding in extraction.findings:
            if (finding.attribute, repr(finding.value)) in known:
                continue
            session.add(
                evidence_item_to_model(
                    _evidence(
                        report, attribute=finding.attribute, value=finding.value,
                        quote=finding.quote, extractor=extraction.provider, model=extraction.model,
                    )
                )
            )
            added += 1
        if extraction.summary:
            session.add(
                evidence_item_to_model(
                    _evidence(report, attribute="summary", value=extraction.summary, quote=None,
                              extractor=extraction.provider, model=extraction.model)
                )
            )
        if extraction.category and ("category", repr(extraction.category)) not in known:
            session.add(
                evidence_item_to_model(
                    _evidence(report, attribute="category", value=extraction.category, quote=None,
                              extractor=extraction.provider, model=extraction.model)
                )
            )
        record_run(
            session, report_id=report.id, stage="extraction", provider=extraction.provider,
            model=extraction.model, status="succeeded", duration_ms=extraction.duration_ms,
            details={
                "findings_added": added,
                "rejected_ungrounded": extraction.rejected,
                "location_phrases": extraction.location_phrases,
            },
        )
        session.flush()

        if incident is not None:
            overrides = incident.fact_overrides or {}
            if extraction.summary and not incident.summary and "summary" not in overrides:
                incident.summary = extraction.summary
            if extraction.category and incident.category == "unknown" and "category" not in overrides:
                incident.category = extraction.category
            if extraction.location_phrases and incident.location_status != "confirmed":
                self._add_landmark_candidates(
                    session, incident, report,
                    [(p, None) for p in extraction.location_phrases],
                    extractor=extraction.provider,
                )
                locations.refresh_incident_location(session, incident)
            self._triage._triage_with_session(incident.id, session, actor_id=None)
            append_audit(
                session,
                action="report.enriched",
                actor_id=None,
                entity_type="report",
                entity_id=report.id,
                disaster_id=report.disaster_id,
                incident_id=incident.id,
                payload={
                    "provider": extraction.provider,
                    "model": extraction.model,
                    "translated": bool(report.translated_text),
                    "findings_added": added,
                },
            )
        return True


def disaster_accepts_reports(session: Session, disaster_id: uuid.UUID) -> DisasterModel:
    disaster = session.get(DisasterModel, disaster_id)
    if disaster is None:
        raise LookupError("Operation not found")
    if disaster.status != "active":
        raise ValueError("This operation is closed and no longer accepts reports")
    return disaster
