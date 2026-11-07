"""Unit tests for ConservativeIncidentResolver safety thresholds and decision routing."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.application.incident_resolution.models import (
    IncidentCandidate,
    ResolutionDecisionType,
)
from raahat.application.incident_resolution.resolver import ConservativeIncidentResolver
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import IncidentLinkType, ProcessingStatus, SourceType


def _make_report() -> Report:
    return Report(
        id=uuid.uuid4(),
        disaster_id=uuid.uuid4(),
        source_type=SourceType.WEB,
        raw_payload={},
        received_at=datetime.now(timezone.utc),
        client_created_at=datetime.now(timezone.utc),
        idempotency_key=f"rep-{uuid.uuid4().hex}",
        processing_status=ProcessingStatus.PENDING,
    )


class TestConservativeIncidentResolver:
    def test_evaluate_no_candidates_creates_new_incident(self) -> None:
        resolver = ConservativeIncidentResolver()
        report = _make_report()
        decision = resolver.evaluate(report, candidates=[])

        assert decision.decision_type == ResolutionDecisionType.CREATE_NEW
        assert decision.matched_incident_id is None
        assert decision.requires_review is False
        assert "No candidate incidents found" in decision.rationale

    def test_evaluate_all_candidates_below_review_threshold_creates_new(self) -> None:
        resolver = ConservativeIncidentResolver(review_threshold=0.40)
        report = _make_report()
        cand = IncidentCandidate(
            incident_id=uuid.uuid4(),
            score=0.25,
            spatial_distance_m=1200.0,
        )
        decision = resolver.evaluate(report, candidates=[cand])

        assert decision.decision_type == ResolutionDecisionType.CREATE_NEW
        assert decision.matched_incident_id is None
        assert decision.requires_review is False
        assert "below review threshold" in decision.rationale

    def test_evaluate_high_confidence_auto_link(self) -> None:
        resolver = ConservativeIncidentResolver(
            auto_link_threshold=0.80,
            review_threshold=0.40,
            min_margin=0.15,
            max_auto_distance_m=150.0,
        )
        report = _make_report()
        target_id = uuid.uuid4()
        cand = IncidentCandidate(
            incident_id=target_id,
            score=0.92,
            spatial_distance_m=28.0,
            conflicts=[],
            suggested_link_type=IncidentLinkType.POSSIBLE_DUPLICATE,
        )
        decision = resolver.evaluate(report, candidates=[cand])

        assert decision.decision_type == ResolutionDecisionType.AUTO_LINK
        assert decision.matched_incident_id == target_id
        assert decision.requires_review is False
        assert "High-confidence conservative match" in decision.rationale

    def test_evaluate_contradictions_strictly_routes_to_review(self) -> None:
        resolver = ConservativeIncidentResolver(auto_link_threshold=0.80)
        report = _make_report()
        target_id = uuid.uuid4()
        # Even with high score and close distance, conflicts must force human review
        cand = IncidentCandidate(
            incident_id=target_id,
            score=0.85,
            spatial_distance_m=15.0,
            conflicts=["[HIGH] water_level_trend: rising vs receded"],
            suggested_link_type=IncidentLinkType.CONFLICTING,
        )
        decision = resolver.evaluate(report, candidates=[cand])

        assert decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert decision.matched_incident_id == target_id
        assert decision.requires_review is True
        assert decision.suggested_link_type == IncidentLinkType.CONFLICTING
        assert "Contradictions detected" in decision.rationale

    def test_evaluate_distance_exceeding_auto_limit_routes_to_review(self) -> None:
        resolver = ConservativeIncidentResolver(
            auto_link_threshold=0.80,
            max_auto_distance_m=150.0,
        )
        report = _make_report()
        target_id = uuid.uuid4()
        # Distance is 220m (>150m)
        cand = IncidentCandidate(
            incident_id=target_id,
            score=0.88,
            spatial_distance_m=220.0,
            conflicts=[],
        )
        decision = resolver.evaluate(report, candidates=[cand])

        assert decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert decision.matched_incident_id == target_id
        assert decision.requires_review is True
        assert "exceeds max auto-link limit" in decision.rationale

    def test_evaluate_ambiguous_score_routes_to_review(self) -> None:
        resolver = ConservativeIncidentResolver(
            auto_link_threshold=0.80,
            review_threshold=0.40,
        )
        report = _make_report()
        target_id = uuid.uuid4()
        # Score is 0.65 (between 0.40 and 0.80)
        cand = IncidentCandidate(
            incident_id=target_id,
            score=0.65,
            spatial_distance_m=50.0,
            conflicts=[],
        )
        decision = resolver.evaluate(report, candidates=[cand])

        assert decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert decision.matched_incident_id == target_id
        assert decision.requires_review is True
        assert "ambiguous range" in decision.rationale

    def test_evaluate_ambiguous_margin_between_candidates_routes_to_review(self) -> None:
        resolver = ConservativeIncidentResolver(
            auto_link_threshold=0.80,
            review_threshold=0.40,
            min_margin=0.15,
        )
        report = _make_report()
        cand1 = IncidentCandidate(
            incident_id=uuid.uuid4(),
            score=0.88,
            spatial_distance_m=40.0,
            conflicts=[],
        )
        cand2 = IncidentCandidate(
            incident_id=uuid.uuid4(),
            score=0.82,
            spatial_distance_m=55.0,
            conflicts=[],
        )
        # Margin is 0.88 - 0.82 = 0.06 (< 0.15 min_margin)
        decision = resolver.evaluate(report, candidates=[cand1, cand2])

        assert decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert decision.matched_incident_id == cand1.incident_id
        assert decision.requires_review is True
        assert "Ambiguous match: margin between top candidates" in decision.rationale
