"""Unit tests for RuleBasedContradictionDetector across evidence items from multiple reports."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.domain.evidence.detector import RuleBasedContradictionDetector
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.shared.enums import VerificationStatus


def _make_item(
    report_id: uuid.UUID,
    attribute: str,
    value: object,
    subject_type: str = "environment",
) -> EvidenceItem:
    return EvidenceItem(
        report_id=report_id,
        subject_type=subject_type,
        attribute=attribute,
        value=value,
        observed_at=datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc),
        verification_status=VerificationStatus.UNVERIFIED,
    )


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------


class TestRuleBasedContradictionDetector:
    def test_water_level_trend_rising_vs_receded_is_high_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1 = uuid.uuid4()
        r2 = uuid.uuid4()

        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "receded"),
        ]

        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert c.conflict_type == "trend_conflict"
        assert c.severity == "high"
        assert c.attribute == "water_level_trend"
        assert set(c.report_ids) == {r1, r2}
        assert "rising" in c.description or "receded" in c.description

    def test_water_level_trend_rising_vs_falling_is_high_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "falling"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].severity == "high"
        assert contradictions[0].conflict_type == "trend_conflict"

    def test_water_level_trend_stable_vs_receded_is_medium_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "stable"),
            _make_item(r2, "water_level_trend", "receded"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].severity == "medium"

    def test_same_trend_is_not_a_contradiction(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "rising"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_headcount_exact_match_is_not_a_contradiction(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "people_count", 4, subject_type="household"),
            _make_item(r2, "people_count", 4, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_headcount_small_divergence_is_medium_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "people_count", 3, subject_type="household"),
            _make_item(r2, "people_count", 5, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert c.conflict_type == "headcount_divergence"
        assert c.severity == "medium"
        assert "3" in c.description or "5" in c.description

    def test_headcount_large_divergence_is_high_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "people_count", 2, subject_type="household"),
            _make_item(r2, "people_count", 15, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].severity == "high"

    def test_boolean_trapped_status_conflict(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "trapped_status", True, subject_type="household"),
            _make_item(r2, "trapped_status", False, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert c.conflict_type == "boolean_conflict"
        assert c.severity == "high"

    def test_boolean_medical_emergency_conflict(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "medical_emergency", True, subject_type="household"),
            _make_item(r2, "medical_emergency", False, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].conflict_type == "boolean_conflict"
        assert contradictions[0].severity == "high"

    def test_water_depth_large_discrepancy_is_high_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_depth_cm", 50.0),
            _make_item(r2, "water_depth_cm", 200.0),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert c.conflict_type == "numeric_divergence"
        assert c.severity == "high"

    def test_water_depth_moderate_discrepancy_is_medium_severity(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_depth_cm", 100.0),
            _make_item(r2, "water_depth_cm", 155.0),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].severity == "medium"

    def test_water_depth_small_discrepancy_is_not_a_contradiction(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_depth_cm", 100.0),
            _make_item(r2, "water_depth_cm", 120.0),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_landmark_divergence_different_locations(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "landmark_mention", "Shiv Mandir", subject_type="location"),
            _make_item(r2, "landmark_mention", "Gandhi Chowk", subject_type="location"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        assert contradictions[0].conflict_type == "location_divergence"
        assert contradictions[0].severity == "medium"

    def test_landmark_substring_match_is_not_a_contradiction(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "landmark_mention", "Shiv Mandir", subject_type="location"),
            _make_item(r2, "landmark_mention", "near Shiv Mandir", subject_type="location"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_no_contradiction_between_different_attributes(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "people_count", 10, subject_type="household"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_same_report_cannot_contradict_itself(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1 = uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r1, "water_level_trend", "receded"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert contradictions == []

    def test_contradiction_values_dict_contains_both_reports(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "receded"),
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1
        c = contradictions[0]
        assert str(r1) in c.values
        assert str(r2) in c.values
        assert set(c.values.values()) == {"rising", "receded"}

    def test_multiple_contradictions_across_three_reports(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "receded"),
            _make_item(r3, "water_level_trend", "falling"),
        ]
        contradictions = detector.detect_contradictions(items)
        # r1-r2 (rising vs receded) and r1-r3 (rising vs falling) are both contradictions
        assert len(contradictions) == 2
        assert all(c.conflict_type == "trend_conflict" for c in contradictions)

    def test_no_duplicate_contradiction_pairs(self) -> None:
        """The same (item_a, item_b, attribute) pair should not produce duplicate Contradiction records."""
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "receded"),
            _make_item(r1, "water_level_trend", "rising"),  # Same report, same value
        ]
        contradictions = detector.detect_contradictions(items)
        assert len(contradictions) == 1


# ---------------------------------------------------------------------------
# Corroboration detection
# ---------------------------------------------------------------------------


class TestCorroborationDetection:
    def test_two_reports_agree_on_trend(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r2, "water_level_trend", "rising"),
        ]
        corroborations = detector.detect_corroborations(items)
        assert len(corroborations) == 1
        c = corroborations[0]
        assert c.attribute == "water_level_trend"
        assert c.value == "rising"
        assert c.agreement_count == 2
        assert set(c.report_ids) == {r1, r2}

    def test_single_report_does_not_corroborate(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1 = uuid.uuid4()
        items = [_make_item(r1, "water_level_trend", "rising")]
        corroborations = detector.detect_corroborations(items)
        assert corroborations == []

    def test_three_reports_agree_on_headcount(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2, r3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "people_count", 6, subject_type="household"),
            _make_item(r2, "people_count", 6, subject_type="household"),
            _make_item(r3, "people_count", 6, subject_type="household"),
        ]
        corroborations = detector.detect_corroborations(items)
        assert len(corroborations) == 1
        assert corroborations[0].agreement_count == 3

    def test_different_values_do_not_corroborate(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "people_count", 3, subject_type="household"),
            _make_item(r2, "people_count", 7, subject_type="household"),
        ]
        corroborations = detector.detect_corroborations(items)
        assert corroborations == []

    def test_duplicate_evidence_from_same_report_counts_once(self) -> None:
        detector = RuleBasedContradictionDetector()
        r1, r2 = uuid.uuid4(), uuid.uuid4()
        items = [
            _make_item(r1, "water_level_trend", "rising"),
            _make_item(r1, "water_level_trend", "rising"),  # Same report duplicate
            _make_item(r2, "water_level_trend", "rising"),
        ]
        corroborations = detector.detect_corroborations(items)
        assert len(corroborations) == 1
        assert corroborations[0].agreement_count == 2  # only 2 distinct reports

