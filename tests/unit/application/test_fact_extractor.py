"""Unit tests for EvidenceGraphFactExtractor observation aggregation and uncertainty preservation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from raahat.application.triage.extractor import EvidenceGraphFactExtractor
from raahat.domain.evidence.evidence import (
    Contradiction,
    EvidenceGraph,
    EvidenceItem,
    EvidenceSpan,
)


class TestEvidenceGraphFactExtractor:
    @pytest.fixture
    def extractor(self) -> EvidenceGraphFactExtractor:
        return EvidenceGraphFactExtractor()

    def test_extract_all_fields_from_evidence(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        rep_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        items = [
            EvidenceItem(
                report_id=rep_id,
                subject_type="environment",
                attribute="water_level_trend",
                value="rising",
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="environment",
                attribute="water_depth_cm",
                value=85.0,
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="household",
                attribute="current_floor",
                value="ground",
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="household",
                attribute="people_count",
                value=4,
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="household",
                attribute="trapped_status",
                value=True,
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="household",
                attribute="medical_emergency",
                value=True,
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="environment",
                attribute="hazard",
                value="downed_power_line",
                observed_at=now,
            ),
            EvidenceItem(
                report_id=rep_id,
                subject_type="need",
                attribute="relief_need",
                value="drinking_water",
                observed_at=now,
            ),
        ]

        facts = extractor.extract_from_evidence(items)
        assert facts.water_level_trend == "rising"
        assert facts.water_depth_cm == 85.0
        assert facts.current_floor == "ground"
        assert facts.people_count == 4
        assert facts.trapped_status is True
        assert facts.medical_emergency is True
        assert "downed_power_line" in facts.hazards
        assert "drinking_water" in facts.relief_needs
        assert facts.last_contact_time == now

    def test_conservative_worst_case_aggregation(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        """When multiple reports report differing trends, depths, and counts, safety rules pick worst case."""
        rep1 = uuid.uuid4()
        rep2 = uuid.uuid4()

        items = [
            # One report says stable, another says rising -> rising picked
            EvidenceItem(report_id=rep1, subject_type="env", attribute="water_level_trend", value="stable"),
            EvidenceItem(report_id=rep2, subject_type="env", attribute="water_level_trend", value="rising"),
            # One report says 40cm, another says 110cm -> 110cm picked
            EvidenceItem(report_id=rep1, subject_type="env", attribute="water_depth_cm", value=40.0),
            EvidenceItem(report_id=rep2, subject_type="env", attribute="water_depth_cm", value=110.0),
            # One report says 2 people, another says 7 people -> 7 people picked
            EvidenceItem(report_id=rep1, subject_type="hh", attribute="people_count", value=2),
            EvidenceItem(report_id=rep2, subject_type="hh", attribute="people_count", value=7),
            # One report says not trapped, another says trapped -> trapped=True
            EvidenceItem(report_id=rep1, subject_type="hh", attribute="trapped_status", value=False),
            EvidenceItem(report_id=rep2, subject_type="hh", attribute="trapped_status", value=True),
        ]

        facts = extractor.extract_from_evidence(items)
        assert facts.water_level_trend == "rising"
        assert facts.water_depth_cm == 110.0
        assert facts.people_count == 7
        assert facts.trapped_status is True

    def test_life_threatening_medical_keyword_detection(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        rep_id = uuid.uuid4()
        span = EvidenceSpan(text="Elderly patient having severe cardiac chest pain and unconscious")
        item = EvidenceItem(
            report_id=rep_id,
            subject_type="household",
            attribute="medical_emergency",
            value=True,
            spans=(span,),
        )
        facts = extractor.extract_from_evidence([item])
        assert facts.medical_emergency is True
        assert facts.is_life_threatening_medical is True

    def test_vulnerable_persons_detection(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        rep_id = uuid.uuid4()
        items = [
            EvidenceItem(
                report_id=rep_id,
                subject_type="need",
                attribute="relief_need",
                value="baby food and diapers for infant",
            ),
        ]
        facts = extractor.extract_from_evidence(items)
        assert facts.vulnerable_present is True
        assert any("infant" in d or "baby" in d for d in facts.vulnerable_details)

    def test_unknown_fields_preserved_when_unobserved(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        """When attributes are not present in evidence, they remain None and in unknown_fields."""
        rep_id = uuid.uuid4()
        items = [
            EvidenceItem(
                report_id=rep_id,
                subject_type="env",
                attribute="water_level_trend",
                value="stable",
            ),
        ]
        facts = extractor.extract_from_evidence(items)
        assert facts.water_level_trend == "stable"
        assert facts.trapped_status is None
        assert facts.medical_emergency is None
        assert facts.water_depth_cm is None
        assert facts.people_count is None
        assert "trapped_status" in facts.unknown_fields
        assert "medical_emergency" in facts.unknown_fields
        assert "exact_people_count" in facts.unknown_fields
        assert "water_depth_cm" in facts.unknown_fields

    def test_extract_from_evidence_graph_with_contradictions(
        self, extractor: EvidenceGraphFactExtractor
    ) -> None:
        rep1 = uuid.uuid4()
        rep2 = uuid.uuid4()
        item1 = EvidenceItem(report_id=rep1, subject_type="hh", attribute="people_count", value=2)
        item2 = EvidenceItem(report_id=rep2, subject_type="hh", attribute="people_count", value=8)

        contradiction = Contradiction(
            attribute="people_count",
            subject_type="hh",
            evidence_item_ids=(item1.id, item2.id),
            report_ids=(rep1, rep2),
            conflict_type="headcount_divergence",
            severity="high",
            description="Contradicting headcount: 2 vs 8",
            values={str(rep1): 2, str(rep2): 8},
        )

        graph = EvidenceGraph(
            report_ids=(rep1, rep2),
            evidence_items=(item1, item2),
            contradictions=(contradiction,),
        )

        facts = extractor.extract_from_graph(graph)
        assert facts.has_contradictions is True
        assert len(facts.contradiction_reasons) == 1
        assert "people_count" in facts.contradiction_reasons[0]
        assert facts.total_reports_count == 2
