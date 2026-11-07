"""Unit tests for EvidenceGraphService coordinating extraction, persistence, and graph building."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.domain.evidence import (
    EvidenceGraph,
    EvidenceGraphService,
    RuleBasedContradictionDetector,
    StructuredEvidenceExtractor,
)
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import ProcessingStatus, SourceType
from raahat.infrastructure.database.repositories import InMemoryEvidenceRepository


def _make_report(
    payload: dict,
    source_type: SourceType = SourceType.WEB,
    report_id: uuid.UUID | None = None,
) -> Report:
    return Report(
        id=report_id or uuid.uuid4(),
        disaster_id=uuid.uuid4(),
        source_type=source_type,
        raw_payload=payload,
        received_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        client_created_at=datetime(2026, 8, 15, 11, 55, 0, tzinfo=timezone.utc),
        idempotency_key=f"test-{uuid.uuid4().hex}",
        processing_status=ProcessingStatus.PENDING,
    )


def _make_service() -> EvidenceGraphService:
    repo = InMemoryEvidenceRepository()
    return EvidenceGraphService(
        evidence_repo=repo,
        extractor=StructuredEvidenceExtractor(),
        detector=RuleBasedContradictionDetector(),
    )


class TestEvidenceGraphServiceDecompose:
    def test_decompose_report_persists_items(self) -> None:
        service = _make_service()
        report = _make_report({"people_count": 4, "water_level_trend": "rising"})

        items = service.decompose_report(report)

        assert len(items) >= 2
        item_map = {it.attribute: it for it in items}
        assert item_map["people_count"].value == 4
        assert item_map["water_level_trend"].value == "rising"

    def test_decompose_report_links_to_report_id(self) -> None:
        service = _make_service()
        report = _make_report({"trapped_status": True})

        items = service.decompose_report(report)

        assert all(it.report_id == report.id for it in items)

    def test_decompose_report_persist_false_does_not_save(self) -> None:
        repo = InMemoryEvidenceRepository()
        service = EvidenceGraphService(evidence_repo=repo, session_factory=None)
        report = _make_report({"people_count": 3})

        items = service.decompose_report(report, persist=False)

        # Items are returned but not stored
        assert len(items) >= 1
        stored = repo.list_by_report_id(report.id)
        assert stored == []

    def test_decompose_empty_payload_produces_no_items(self) -> None:
        service = _make_service()
        report = _make_report({})
        items = service.decompose_report(report)
        assert items == []


class TestEvidenceGraphServiceBuildGraph:
    def test_build_graph_with_contradictions(self) -> None:
        service = _make_service()

        r1 = _make_report({"water_level_trend": "rising", "people_count": 4})
        r2 = _make_report({"water_level_trend": "receded", "people_count": 10})

        service.decompose_report(r1)
        service.decompose_report(r2)

        graph = service.build_evidence_graph([r1.id, r2.id])

        assert isinstance(graph, EvidenceGraph)
        assert len(graph.evidence_items) >= 4
        assert set(graph.report_ids) == {r1.id, r2.id}

        # Confirm rising vs receded contradiction was detected
        trend_contradictions = [c for c in graph.contradictions if c.attribute == "water_level_trend"]
        assert len(trend_contradictions) == 1
        assert trend_contradictions[0].conflict_type == "trend_conflict"
        assert trend_contradictions[0].severity == "high"

        # Confirm headcount divergence was detected
        hc_contradictions = [c for c in graph.contradictions if c.attribute == "people_count"]
        assert len(hc_contradictions) == 1
        assert hc_contradictions[0].conflict_type == "headcount_divergence"

    def test_build_graph_with_corroborations(self) -> None:
        service = _make_service()

        r1 = _make_report({"water_level_trend": "rising", "medical_emergency": True})
        r2 = _make_report({"water_level_trend": "rising", "medical_emergency": True})
        r3 = _make_report({"water_level_trend": "rising"})

        service.decompose_report(r1)
        service.decompose_report(r2)
        service.decompose_report(r3)

        graph = service.build_evidence_graph([r1.id, r2.id, r3.id])

        trend_corroborations = [c for c in graph.corroborations if c.attribute == "water_level_trend"]
        assert len(trend_corroborations) == 1
        assert trend_corroborations[0].agreement_count == 3

        medical_corroborations = [c for c in graph.corroborations if c.attribute == "medical_emergency"]
        assert len(medical_corroborations) == 1
        assert medical_corroborations[0].agreement_count == 2

    def test_build_empty_graph_for_undecomposed_reports(self) -> None:
        service = _make_service()
        r1, r2 = uuid.uuid4(), uuid.uuid4()

        graph = service.build_evidence_graph([r1, r2])

        assert len(graph.evidence_items) == 0
        assert len(graph.contradictions) == 0
        assert len(graph.corroborations) == 0

    def test_contradictions_are_flagged_not_silently_resolved(self) -> None:
        """Core constraint: contradictions must surface as Contradiction records, never discarded."""
        service = _make_service()

        r1 = _make_report({"trapped_status": True})
        r2 = _make_report({"trapped_status": False})

        service.decompose_report(r1)
        service.decompose_report(r2)

        graph = service.build_evidence_graph([r1.id, r2.id])

        boolean_conflicts = [c for c in graph.contradictions if c.attribute == "trapped_status"]
        assert len(boolean_conflicts) == 1
        c = boolean_conflicts[0]
        assert c.conflict_type == "boolean_conflict"
        # Both values are preserved in the graph — not silently dropped
        assert True in c.values.values()
        assert False in c.values.values()


class TestEvidenceProvenance:
    def test_provenance_resolution_via_explicit_report(self) -> None:
        repo = InMemoryEvidenceRepository()
        service = EvidenceGraphService(evidence_repo=repo, session_factory=None)

        report = _make_report(
            {
                "people_count": 7,
                "location": "Nehru Nagar",
            },
            source_type=SourceType.VOLUNTEER,
        )
        report = report.model_copy(update={"source_identity": "Volunteer Ravi", "device_id": uuid.uuid4()})
        items = service.decompose_report(report)
        hc_item = next(it for it in items if it.attribute == "people_count")

        provenance = service.get_evidence_provenance(hc_item.id, report=report)

        assert provenance is not None
        assert provenance.evidence_id == hc_item.id
        assert provenance.report_id == report.id
        assert provenance.source_type == SourceType.VOLUNTEER
        assert provenance.source_identity == "Volunteer Ravi"
        assert provenance.attribute == "people_count"
        assert provenance.value == 7
        assert provenance.received_at == report.received_at
        assert provenance.client_created_at == report.client_created_at

    def test_provenance_returns_none_for_nonexistent_evidence(self) -> None:
        repo = InMemoryEvidenceRepository()
        service = EvidenceGraphService(evidence_repo=repo, session_factory=None)

        result = service.get_evidence_provenance(uuid.uuid4())
        assert result is None

    def test_provenance_spans_are_included(self) -> None:
        repo = InMemoryEvidenceRepository()
        service = EvidenceGraphService(evidence_repo=repo, session_factory=None)

        report = _make_report({"people_count": 3})
        items = service.decompose_report(report)
        hc_item = next(it for it in items if it.attribute == "people_count")

        provenance = service.get_evidence_provenance(hc_item.id, report=report)

        assert provenance is not None
        assert len(provenance.spans) >= 1
        assert any("people_count" in s.reference.get("source_field", "") for s in provenance.spans)
