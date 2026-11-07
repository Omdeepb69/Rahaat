"""Evidence graph application service: report decomposition, provenance, and conflict fusion."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.evidence.detector import ContradictionDetector, RuleBasedContradictionDetector
from raahat.domain.evidence.evidence import (
    Contradiction,
    Corroboration,
    EvidenceGraph,
    EvidenceItem,
    EvidenceProvenance,
)
from raahat.domain.evidence.extractor import ReportEvidenceExtractor, StructuredEvidenceExtractor
from raahat.domain.evidence.repository import EvidenceRepository, InMemoryEvidenceRepository
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import ProcessingStatus, SourceType
from raahat.infrastructure.database.models.report import ReportModel

logger = logging.getLogger(__name__)


def _model_to_report(model: ReportModel) -> Report:
    """Helper to convert ReportModel to domain Report."""
    return Report(
        id=model.id,
        disaster_id=model.disaster_id,
        source_type=SourceType(model.source_type),
        source_event_id=model.source_event_id,
        source_identity=model.source_identity,
        device_id=model.device_id,
        channel_reference=model.channel_reference,
        raw_payload=model.raw_payload,
        received_at=model.received_at,
        client_created_at=model.client_created_at,
        language_code=model.language_code,
        processing_status=ProcessingStatus(model.processing_status),
        idempotency_key=model.idempotency_key,
    )


class EvidenceGraphService:
    """Coordinates report decomposition into atomic claims, provenance tracking, and conflict detection."""

    def __init__(
        self,
        evidence_repo: Optional[EvidenceRepository] = None,
        extractor: Optional[ReportEvidenceExtractor] = None,
        detector: Optional[ContradictionDetector] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._evidence_repo = evidence_repo or InMemoryEvidenceRepository()
        self._extractor = extractor or StructuredEvidenceExtractor()
        self._detector = detector or RuleBasedContradictionDetector()
        self._session_factory = session_factory

    def decompose_report(
        self,
        report: Report,
        persist: bool = True,
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        """Extract atomic evidence claims from a report with source spans and optional persistence."""
        items = self._extractor.extract(report)
        if persist and items:
            return self._evidence_repo.save_all(items, session=session)
        return items

    def detect_contradictions(
        self,
        items: list[EvidenceItem],
    ) -> list[Contradiction]:
        """Detect pairwise factual conflicts across evidence claims from distinct reports."""
        return self._detector.detect_contradictions(items)

    def detect_corroborations(
        self,
        items: list[EvidenceItem],
    ) -> list[Corroboration]:
        """Detect multi-report corroborations on identical claims."""
        return self._detector.detect_corroborations(items)

    def build_evidence_graph(
        self,
        report_ids: list[uuid.UUID],
        session: Optional[Session] = None,
    ) -> EvidenceGraph:
        """Construct the full evidence graph across multiple reports including conflicts and agreements."""
        items = self._evidence_repo.list_by_report_ids(report_ids, session=session)
        contradictions = self.detect_contradictions(items)
        corroborations = self.detect_corroborations(items)

        return EvidenceGraph(
            report_ids=tuple(report_ids),
            evidence_items=tuple(items),
            contradictions=tuple(contradictions),
            corroborations=tuple(corroborations),
        )

    def get_evidence_provenance(
        self,
        evidence_id: uuid.UUID,
        report: Optional[Report] = None,
        session: Optional[Session] = None,
    ) -> Optional[EvidenceProvenance]:
        """Trace the full audit provenance of an evidence item back to its origin report."""
        item = self._evidence_repo.get_by_id(evidence_id, session=session)
        if item is None:
            return None

        # Resolve report if not explicitly provided
        resolved_report = report
        if resolved_report is None and self._session_factory is not None:
            if session is not None:
                rep_model = session.get(ReportModel, item.report_id)
                if rep_model is not None:
                    resolved_report = _model_to_report(rep_model)
            else:
                with self._session_factory() as sess:
                    rep_model = sess.get(ReportModel, item.report_id)
                    if rep_model is not None:
                        resolved_report = _model_to_report(rep_model)

        if resolved_report is None:
            logger.warning(
                "Cannot build full provenance: report %s not found for evidence %s",
                item.report_id,
                evidence_id,
            )
            return None

        return EvidenceProvenance(
            evidence_id=item.id,
            report_id=resolved_report.id,
            source_type=resolved_report.source_type,
            source_identity=resolved_report.source_identity,
            device_id=resolved_report.device_id,
            channel_reference=resolved_report.channel_reference,
            client_created_at=resolved_report.client_created_at,
            received_at=resolved_report.received_at,
            attribute=item.attribute,
            value=item.value,
            spans=item.spans,
        )

