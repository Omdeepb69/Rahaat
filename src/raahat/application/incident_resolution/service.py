"""Incident resolution application service orchestrating candidate matching and linking."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.evidence.extractor import StructuredEvidenceExtractor
from raahat.domain.incidents.incident import Incident, IncidentLink, IncidentReportLink
from raahat.domain.incidents.repository import IncidentRepository, InMemoryIncidentRepository
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import (
    IncidentLinkType,
    IncidentStatus,
    PriorityLevel,
    RelationshipType,
)
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.location import LocationHypothesisModel

from .matcher import ConservativeIncidentMatcher, extract_coordinates
from .models import ResolutionDecisionType, ResolutionResult
from .protocol import IncidentMatcher, IncidentResolver
from .resolver import ConservativeIncidentResolver

logger = logging.getLogger(__name__)


class IncidentResolutionService:
    """Coordinates matching, safety evaluation, and persistent linking for incoming reports."""

    def __init__(
        self,
        matcher: Optional[IncidentMatcher] = None,
        resolver: Optional[IncidentResolver] = None,
        incident_repo: Optional[IncidentRepository] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
        extractor: Optional[StructuredEvidenceExtractor] = None,
    ) -> None:
        self.matcher = matcher or ConservativeIncidentMatcher()
        self.resolver = resolver or ConservativeIncidentResolver()
        self.incident_repo = incident_repo or InMemoryIncidentRepository()
        self.session_factory = session_factory
        self.extractor = extractor or StructuredEvidenceExtractor()

    def resolve_report(
        self,
        report: Report,
        evidence_items: Optional[list[EvidenceItem]] = None,
        session: Optional[Session] = None,
    ) -> ResolutionResult:
        """Process an incoming report through matching, safety resolution, and link persistence."""
        if evidence_items is None:
            evidence_items = self.extractor.extract(report)

        if session is not None:
            return self._resolve_with_session(report, evidence_items, session)
        elif self.session_factory is not None:
            with self.session_factory() as new_session:
                res = self._resolve_with_session(report, evidence_items, new_session)
                new_session.commit()
                return res
        else:
            return self._resolve_in_memory(report, evidence_items)

    def _resolve_with_session(
        self,
        report: Report,
        evidence_items: list[EvidenceItem],
        session: Session,
    ) -> ResolutionResult:
        candidates = self.matcher.find_candidates(report, evidence_items, session=session)
        decision = self.resolver.evaluate(report, candidates)

        # 1. High-confidence auto-link
        if decision.decision_type == ResolutionDecisionType.AUTO_LINK:
            assert decision.matched_incident_id is not None
            target_inc_id = decision.matched_incident_id

            report_link = IncidentReportModel(
                incident_id=target_inc_id,
                report_id=report.id,
                relationship=RelationshipType.DUPLICATE.value,
                linked_by="system:conservative_matcher",
            )
            session.add(report_link)

            inc_m = session.get(IncidentModel, target_inc_id)
            if inc_m:
                session.flush()

            logger.info(
                "Report %s auto-linked to incident %s (score: %.2f)",
                report.id,
                target_inc_id,
                candidates[0].score if candidates else 0.0,
            )
            return ResolutionResult(
                decision=decision,
                incident_id=target_inc_id,
                is_new_incident=False,
                link_id=None,
            )

        # 2. Ambiguous match requiring human review
        elif decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW:
            new_inc_id = uuid.uuid4()
            new_inc_m = IncidentModel(
                id=new_inc_id,
                disaster_id=report.disaster_id,
                status=IncidentStatus.UNVERIFIED.value,
                operational_priority=PriorityLevel.UNASSESSED.value,
                severity_facts={},
            )
            session.add(new_inc_m)
            session.flush()

            rep_link_m = IncidentReportModel(
                incident_id=new_inc_id,
                report_id=report.id,
                relationship=RelationshipType.DIRECT.value,
                linked_by="system:resolution_service",
            )
            session.add(rep_link_m)

            coords = extract_coordinates(report)
            if coords:
                hyp_m = LocationHypothesisModel(
                    id=uuid.uuid4(),
                    incident_id=new_inc_id,
                    location=f"SRID=4326;{coords.to_wkt()}",
                    candidate_label="report_initial_pin",
                    probability=None,
                    uncertainty_radius_m=None,
                    verification_status="unverified",
                )
                session.add(hyp_m)

            link_id: Optional[uuid.UUID] = None
            if candidates and decision.matched_incident_id:
                link_id = uuid.uuid4()
                link_type_str = (
                    decision.suggested_link_type.value
                    if decision.suggested_link_type
                    else IncidentLinkType.POSSIBLE_DUPLICATE.value
                )
                inc_link_m = IncidentLinkModel(
                    id=link_id,
                    incident_a_id=new_inc_id,
                    incident_b_id=decision.matched_incident_id,
                    link_type=link_type_str,
                    confidence=candidates[0].score,
                    status="pending_review",
                )
                session.add(inc_link_m)

            session.flush()
            logger.info(
                "Report %s created incident %s; routed to review queue with link to %s",
                report.id,
                new_inc_id,
                decision.matched_incident_id,
            )
            return ResolutionResult(
                decision=decision,
                incident_id=new_inc_id,
                is_new_incident=True,
                link_id=link_id,
            )

        # 3. Create new incident
        else:
            new_inc_id = uuid.uuid4()
            new_inc_m = IncidentModel(
                id=new_inc_id,
                disaster_id=report.disaster_id,
                status=IncidentStatus.UNVERIFIED.value,
                operational_priority=PriorityLevel.UNASSESSED.value,
                severity_facts={},
            )
            session.add(new_inc_m)
            session.flush()

            rep_link_m = IncidentReportModel(
                incident_id=new_inc_id,
                report_id=report.id,
                relationship=RelationshipType.DIRECT.value,
                linked_by="system:resolution_service",
            )
            session.add(rep_link_m)

            coords = extract_coordinates(report)
            if coords:
                hyp_m = LocationHypothesisModel(
                    id=uuid.uuid4(),
                    incident_id=new_inc_id,
                    location=f"SRID=4326;{coords.to_wkt()}",
                    candidate_label="report_initial_pin",
                    probability=None,
                    uncertainty_radius_m=None,
                    verification_status="unverified",
                )
                session.add(hyp_m)

            session.flush()
            logger.info("Report %s created independent incident %s", report.id, new_inc_id)
            return ResolutionResult(
                decision=decision,
                incident_id=new_inc_id,
                is_new_incident=True,
                link_id=None,
            )

    def _resolve_in_memory(
        self,
        report: Report,
        evidence_items: list[EvidenceItem],
    ) -> ResolutionResult:
        candidates = self.matcher.find_candidates(report, evidence_items)
        decision = self.resolver.evaluate(report, candidates)

        if decision.decision_type == ResolutionDecisionType.AUTO_LINK:
            assert decision.matched_incident_id is not None
            target_inc_id = decision.matched_incident_id

            self.incident_repo.save_report_link(IncidentReportLink(
                incident_id=target_inc_id,
                report_id=report.id,
                relationship=RelationshipType.DUPLICATE,
                linked_by="system:conservative_matcher",
            ))

            return ResolutionResult(
                decision=decision,
                incident_id=target_inc_id,
                is_new_incident=False,
                link_id=None,
            )

        elif decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW:
            new_inc = Incident(
                id=uuid.uuid4(),
                disaster_id=report.disaster_id,
                status=IncidentStatus.UNVERIFIED,
                operational_priority=PriorityLevel.UNASSESSED,
            )
            self.incident_repo.save(new_inc)

            self.incident_repo.save_report_link(IncidentReportLink(
                incident_id=new_inc.id,
                report_id=report.id,
                relationship=RelationshipType.DIRECT,
                linked_by="system:resolution_service",
            ))

            link_id: Optional[uuid.UUID] = None
            if candidates and decision.matched_incident_id:
                link_id = uuid.uuid4()
                link = IncidentLink(
                    id=link_id,
                    incident_a_id=new_inc.id,
                    incident_b_id=decision.matched_incident_id,
                    link_type=decision.suggested_link_type or IncidentLinkType.POSSIBLE_DUPLICATE,
                    confidence=candidates[0].score,
                    status="pending_review",
                )
                self.incident_repo.save_incident_link(link)

            return ResolutionResult(
                decision=decision,
                incident_id=new_inc.id,
                is_new_incident=True,
                link_id=link_id,
            )

        else:
            new_inc = Incident(
                id=uuid.uuid4(),
                disaster_id=report.disaster_id,
                status=IncidentStatus.UNVERIFIED,
                operational_priority=PriorityLevel.UNASSESSED,
            )
            self.incident_repo.save(new_inc)

            self.incident_repo.save_report_link(IncidentReportLink(
                incident_id=new_inc.id,
                report_id=report.id,
                relationship=RelationshipType.DIRECT,
                linked_by="system:resolution_service",
            ))

            return ResolutionResult(
                decision=decision,
                incident_id=new_inc.id,
                is_new_incident=True,
                link_id=None,
            )
