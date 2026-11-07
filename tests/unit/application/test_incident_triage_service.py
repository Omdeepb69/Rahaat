"""Unit tests for IncidentTriageService orchestration and audit logging."""
from __future__ import annotations

import uuid

import pytest

from raahat.application.triage.service import IncidentTriageService
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.evidence.repository import InMemoryEvidenceRepository
from raahat.domain.incidents.incident import Incident, IncidentReportLink
from raahat.domain.incidents.repository import InMemoryIncidentRepository
from raahat.domain.shared.enums import (
    IncidentStatus,
    PriorityLevel,
    RelationshipType,
)
from raahat.domain.triage.facts import SeverityFacts
from raahat.infrastructure.database.repositories.audit import InMemoryAuditRepository


class TestIncidentTriageService:
    @pytest.fixture
    def incident_repo(self) -> InMemoryIncidentRepository:
        return InMemoryIncidentRepository()

    @pytest.fixture
    def evidence_repo(self) -> InMemoryEvidenceRepository:
        return InMemoryEvidenceRepository()

    @pytest.fixture
    def audit_repo(self) -> InMemoryAuditRepository:
        return InMemoryAuditRepository()

    @pytest.fixture
    def service(
        self,
        incident_repo: InMemoryIncidentRepository,
        evidence_repo: InMemoryEvidenceRepository,
        audit_repo: InMemoryAuditRepository,
    ) -> IncidentTriageService:
        return IncidentTriageService(
            incident_repo=incident_repo,
            evidence_repo=evidence_repo,
            audit_repo=audit_repo,
        )

    def test_triage_incident_success(
        self,
        service: IncidentTriageService,
        incident_repo: InMemoryIncidentRepository,
        evidence_repo: InMemoryEvidenceRepository,
        audit_repo: InMemoryAuditRepository,
    ) -> None:
        disaster_id = uuid.uuid4()
        inc = incident_repo.save(
            Incident(
                disaster_id=disaster_id,
                status=IncidentStatus.UNVERIFIED,
                operational_priority=PriorityLevel.UNASSESSED,
            )
        )
        rep_id = uuid.uuid4()
        incident_repo.save_report_link(
            IncidentReportLink(
                incident_id=inc.id,
                report_id=rep_id,
                relationship=RelationshipType.DIRECT,
                linked_by="test",
            )
        )

        # Add evidence: rising water and trapped occupants
        evidence_repo.save_all([
            EvidenceItem(
                report_id=rep_id,
                subject_type="environment",
                attribute="water_level_trend",
                value="rising",
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="household",
                attribute="trapped_status",
                value=True,
            ),
        ])

        updated_inc, assessment = service.triage_incident(inc.id)

        # Should be CRITICAL_REVIEW due to trapped + rising water
        assert updated_inc.operational_priority == PriorityLevel.CRITICAL_REVIEW
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "rising_water_with_trapped_occupants" in assessment.reasons
        assert assessment.requires_human_review is True
        assert updated_inc.severity_facts["water_level_trend"] == "rising"
        assert updated_inc.severity_facts["trapped_status"] is True

        # Check audit event
        assert len(audit_repo.events) == 1
        event = audit_repo.events[0]
        assert event.action == "incident.triaged"
        assert event.entity_type == "incident"
        assert event.entity_id == inc.id
        assert event.payload["new_priority"] == "critical_review"
        assert "rising_water_with_trapped_occupants" in event.payload["reasons"]

    def test_triage_incident_contradiction_escalates_to_critical_review(
        self,
        service: IncidentTriageService,
        incident_repo: InMemoryIncidentRepository,
        evidence_repo: InMemoryEvidenceRepository,
    ) -> None:
        disaster_id = uuid.uuid4()
        inc = incident_repo.save(
            Incident(
                disaster_id=disaster_id,
                status=IncidentStatus.UNVERIFIED,
                operational_priority=PriorityLevel.UNASSESSED,
            )
        )
        rep1 = uuid.uuid4()
        rep2 = uuid.uuid4()
        incident_repo.save_report_link(
            IncidentReportLink(incident_id=inc.id, report_id=rep1, relationship=RelationshipType.DIRECT, linked_by="test")
        )
        incident_repo.save_report_link(
            IncidentReportLink(incident_id=inc.id, report_id=rep2, relationship=RelationshipType.DIRECT, linked_by="test")
        )

        # Contradicting trapped status: report 1 says True, report 2 says False
        evidence_repo.save_all([
            EvidenceItem(report_id=rep1, subject_type="hh", attribute="trapped_status", value=True),
            EvidenceItem(report_id=rep2, subject_type="hh", attribute="trapped_status", value=False),
        ])

        updated_inc, assessment = service.triage_incident(inc.id)
        assert updated_inc.operational_priority == PriorityLevel.CRITICAL_REVIEW
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "evidence_contradiction_detected" in assessment.reasons

    def test_triage_nonexistent_incident_raises_value_error(
        self, service: IncidentTriageService
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            service.triage_incident(uuid.uuid4())

    def test_assess_facts_direct_helper(
        self, service: IncidentTriageService
    ) -> None:
        facts = SeverityFacts(water_level_trend="rising")
        assessment = service.assess_facts(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "rising_water_level" in assessment.reasons
