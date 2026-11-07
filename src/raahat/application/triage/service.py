"""Incident triage application service orchestrating fact extraction, deterministic safety policy, and audit logging."""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.triage.extractor import EvidenceGraphFactExtractor
from raahat.application.triage.protocol import FactExtractor
from raahat.domain.evidence.detector import ContradictionDetector, RuleBasedContradictionDetector
from raahat.domain.evidence.evidence import Contradiction, EvidenceGraph, EvidenceItem
from raahat.domain.evidence.repository import EvidenceRepository, InMemoryEvidenceRepository
from raahat.domain.incidents.incident import Incident
from raahat.domain.incidents.repository import IncidentRepository, InMemoryIncidentRepository
from raahat.domain.shared.enums import IncidentStatus, PriorityLevel
from raahat.domain.triage.assessment import PriorityAssessment
from raahat.domain.triage.facts import SeverityFacts
from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.incident import (
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    InMemoryAuditRepository,
)
from raahat.policies.triage import DeterministicSafetyPriorityPolicy, PriorityPolicy

logger = logging.getLogger(__name__)


def _model_to_incident(model: IncidentModel) -> Incident:
    """Helper converting ORM IncidentModel to frozen domain Incident aggregate."""
    return Incident(
        id=model.id,
        disaster_id=model.disaster_id,
        status=IncidentStatus(model.status),
        operational_priority=PriorityLevel(model.operational_priority),
        severity_facts=dict(model.severity_facts or {}),
        last_confirmed_at=model.last_confirmed_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class IncidentTriageService:
    """Coordinates fact extraction, safety policy evaluation, and incident operational priority updates."""

    def __init__(
        self,
        incident_repo: Optional[IncidentRepository] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
        fact_extractor: Optional[FactExtractor] = None,
        priority_policy: Optional[PriorityPolicy] = None,
        contradiction_detector: Optional[ContradictionDetector] = None,
        audit_repo: Optional[AuditRepository] = None,
        session_factory: Optional[sessionmaker[Session]] = None,
    ) -> None:
        self._incident_repo = incident_repo or InMemoryIncidentRepository()
        self._evidence_repo = evidence_repo or InMemoryEvidenceRepository()
        self._fact_extractor = fact_extractor or EvidenceGraphFactExtractor()
        self._priority_policy = priority_policy or DeterministicSafetyPriorityPolicy()
        self._contradiction_detector = contradiction_detector or RuleBasedContradictionDetector()
        self._audit_repo = audit_repo or InMemoryAuditRepository()
        self._session_factory = session_factory

    def assess_facts(self, facts: SeverityFacts) -> PriorityAssessment:
        """Directly calculate explainable operational priority assessment for given severity facts."""
        return self._priority_policy.assess(facts)

    def extract_facts_from_evidence(
        self,
        evidence_items: Sequence[EvidenceItem],
        contradictions: Sequence[Contradiction] = (),
        total_reports: int = 0,
        unverified_reports_count: int = 0,
    ) -> SeverityFacts:
        """Extract normalized SeverityFacts from atomic evidence items and conflicts."""
        return self._fact_extractor.extract_from_evidence(
            evidence_items=evidence_items,
            contradictions=contradictions,
            total_reports=total_reports,
            unverified_reports_count=unverified_reports_count,
        )

    def extract_facts_from_graph(self, graph: EvidenceGraph) -> SeverityFacts:
        """Extract normalized SeverityFacts from an EvidenceGraph."""
        return self._fact_extractor.extract_from_graph(graph)

    def triage_incident(
        self,
        incident_id: uuid.UUID,
        session: Optional[Session] = None,
        actor_id: Optional[uuid.UUID] = None,
    ) -> tuple[Incident, PriorityAssessment]:
        """Triage an incident: extract evidence facts, run deterministic policy, update incident, and audit."""
        if session is not None:
            return self._triage_with_session(incident_id, session, actor_id=actor_id)
        elif self._session_factory is not None:
            with self._session_factory() as new_session:
                res = self._triage_with_session(incident_id, new_session, actor_id=actor_id)
                new_session.commit()
                return res
        else:
            return self._triage_in_memory(incident_id, actor_id=actor_id)

    def _triage_with_session(
        self,
        incident_id: uuid.UUID,
        session: Session,
        actor_id: Optional[uuid.UUID] = None,
    ) -> tuple[Incident, PriorityAssessment]:
        incident_m = session.get(IncidentModel, incident_id)
        if incident_m is None:
            raise ValueError(f"Incident {incident_id} not found")

        # 1. Fetch linked reports
        links = session.scalars(
            select(IncidentReportModel).where(IncidentReportModel.incident_id == incident_id)
        ).all()
        report_ids = [link.report_id for link in links]

        # 2. Fetch evidence items
        evidence_items = self._evidence_repo.list_by_report_ids(report_ids, session=session)

        # 3. Detect contradictions across evidence items
        contradictions = self._contradiction_detector.detect_contradictions(list(evidence_items))

        # 4. Extract consolidated SeverityFacts
        facts = self._fact_extractor.extract_from_evidence(
            evidence_items=evidence_items,
            contradictions=contradictions,
            total_reports=len(report_ids),
        )

        # 5. Assess operational priority
        assessment = self._priority_policy.assess(facts)

        # 6. Update incident model state
        old_priority = incident_m.operational_priority
        incident_m.operational_priority = assessment.priority.value
        incident_m.severity_facts = facts.model_dump(mode="json")
        incident_m.updated_at = utc_now()
        session.flush()

        # 7. Record tamper-evident audit event
        self._audit_repo.record_event(
            action="incident.triaged",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident_id,
            payload={
                "previous_priority": old_priority,
                "new_priority": assessment.priority.value,
                "reasons": list(assessment.reasons),
                "unknown_fields": list(assessment.unknown_fields),
                "requires_human_review": assessment.requires_human_review,
                "has_contradictions": facts.has_contradictions,
                "reports_count": len(report_ids),
            },
        )

        return _model_to_incident(incident_m), assessment

    def _triage_in_memory(
        self,
        incident_id: uuid.UUID,
        actor_id: Optional[uuid.UUID] = None,
    ) -> tuple[Incident, PriorityAssessment]:
        incident = self._incident_repo.get_by_id(incident_id)
        if incident is None:
            raise ValueError(f"Incident {incident_id} not found")

        report_ids = self._incident_repo.list_reports_for_incident(incident_id)
        evidence_items = self._evidence_repo.list_by_report_ids(report_ids)
        contradictions = self._contradiction_detector.detect_contradictions(list(evidence_items))

        facts = self._fact_extractor.extract_from_evidence(
            evidence_items=evidence_items,
            contradictions=contradictions,
            total_reports=len(report_ids),
        )

        assessment = self._priority_policy.assess(facts)

        old_priority = incident.operational_priority.value
        updated_incident = incident.model_copy(
            update={
                "operational_priority": assessment.priority,
                "severity_facts": facts.model_dump(mode="json"),
                "updated_at": utc_now(),
            }
        )
        self._incident_repo.save(updated_incident)

        self._audit_repo.record_event(
            action="incident.triaged",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident_id,
            payload={
                "previous_priority": old_priority,
                "new_priority": assessment.priority.value,
                "reasons": list(assessment.reasons),
                "unknown_fields": list(assessment.unknown_fields),
                "requires_human_review": assessment.requires_human_review,
                "has_contradictions": facts.has_contradictions,
                "reports_count": len(report_ids),
            },
        )

        return updated_incident, assessment
