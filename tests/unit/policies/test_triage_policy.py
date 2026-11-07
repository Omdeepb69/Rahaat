"""Unit tests for DeterministicSafetyPriorityPolicy and explicit uncertainty preservation rules."""
from __future__ import annotations

import pytest

from raahat.domain.shared.enums import PriorityLevel
from raahat.domain.triage.facts import SeverityFacts
from raahat.policies.triage import DeterministicSafetyPriorityPolicy


class TestDeterministicSafetyPriorityPolicy:
    @pytest.fixture
    def policy(self) -> DeterministicSafetyPriorityPolicy:
        return DeterministicSafetyPriorityPolicy()

    # =========================================================================
    # Phase 1: CRITICAL_REVIEW Rule Tests
    # =========================================================================

    def test_critical_medical_emergency_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            is_life_threatening_medical=True,
            water_depth_cm=20.0,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "critical_medical_emergency" in assessment.reasons
        assert assessment.requires_human_review is True

    def test_medical_emergency_with_rising_water_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            medical_emergency=True,
            water_level_trend="rising",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "medical_need_with_trapped_or_rising_water" in assessment.reasons
        assert assessment.requires_human_review is True

    def test_medical_emergency_with_trapped_occupants_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            medical_emergency=True,
            trapped_status=True,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "medical_need_with_trapped_or_rising_water" in assessment.reasons
        assert assessment.requires_human_review is True

    def test_water_entering_occupied_floor_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_entering_occupied_floor=True,
            current_floor="first",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "water_entering_occupied_floor" in assessment.reasons
        assert assessment.requires_human_review is True

    def test_ground_floor_deep_submersion_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            current_floor="ground",
            water_depth_cm=120.0,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "ground_floor_submerged_exceeds_threshold" in assessment.reasons

    def test_trapped_occupants_with_rising_water_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            trapped_status=True,
            water_level_trend="rising",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "rising_water_with_trapped_occupants" in assessment.reasons

    def test_acute_hazards_trigger_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        for hazard in ("live_wire_in_flood", "gas_leak_detected", "structural_collapse_imminent", "landslide"):
            facts = SeverityFacts(hazards=(hazard,))
            assessment = policy.assess(facts)
            assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
            assert any(r.startswith("acute_hazard:") for r in assessment.reasons)

    def test_high_headcount_trapped_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            trapped_status=True,
            people_count=6,
            water_level_trend="stable",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "high_headcount_trapped" in assessment.reasons

    def test_vulnerable_persons_trapped_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            trapped_status=True,
            vulnerable_present=True,
            vulnerable_details=("infant", "elderly"),
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "vulnerable_persons_trapped" in assessment.reasons

    def test_evidence_contradiction_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            has_contradictions=True,
            contradiction_reasons=("Conflict on trapped_status: report 1 claims trapped, report 2 claims evacuated",),
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "evidence_contradiction_detected" in assessment.reasons

    def test_deep_rising_flood_with_unknown_occupancy_triggers_critical_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        # Unknown never lowers priority: deep rising flood without confirmed occupancy is critical
        facts = SeverityFacts(
            water_level_trend="rising",
            water_depth_cm=160.0,
            trapped_status=None,  # unknown
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "deep_rising_flood_with_unknown_occupants" in assessment.reasons

    # =========================================================================
    # Phase 2: URGENT Rule Tests
    # =========================================================================

    def test_trapped_occupants_stable_water_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            trapped_status=True,
            water_level_trend="stable",
            water_depth_cm=40.0,
            people_count=2,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "occupants_trapped" in assessment.reasons

    def test_medical_emergency_standard_flood_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            medical_emergency=True,
            water_level_trend="stable",
            water_depth_cm=30.0,
            trapped_status=False,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "medical_need_reported" in assessment.reasons

    def test_rising_water_level_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_level_trend="rising",
            trapped_status=False,
            medical_emergency=False,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "rising_water_level" in assessment.reasons

    def test_significant_water_depth_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_depth_cm=110.0,
            current_floor="second",
            trapped_status=False,
            water_level_trend="stable",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "significant_water_depth" in assessment.reasons

    def test_vulnerable_persons_in_hazard_area_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            vulnerable_present=True,
            water_depth_cm=50.0,
            trapped_status=False,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "vulnerable_persons_in_hazard_area" in assessment.reasons

    def test_non_acute_hazards_trigger_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            hazards=("downed_telephone_cable", "floating_debris"),
            trapped_status=False,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert any(r.startswith("hazard_reported:") for r in assessment.reasons)

    def test_water_depth_with_unverified_occupant_triggers_urgent(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        # Unknown never lowers priority: water depth 70cm with unknown occupancy
        facts = SeverityFacts(
            water_depth_cm=70.0,
            trapped_status=None,  # unknown
            water_level_trend="stable",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.URGENT
        assert "water_depth_with_unverified_occupant_safety" in assessment.reasons

    # =========================================================================
    # Phase 3: STANDARD Rule Tests
    # =========================================================================

    def test_shallow_water_triggers_standard(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_depth_cm=30.0,
            water_level_trend="stable",
            trapped_status=False,
            medical_emergency=False,
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.STANDARD
        assert "shallow_or_stable_water" in assessment.reasons

    def test_relief_needs_trigger_standard(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            relief_needs=("drinking_water", "dry_food", "tarpaulin"),
            trapped_status=False,
            medical_emergency=False,
            water_level_trend="stable",
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.STANDARD
        assert any(r.startswith("relief_need:") for r in assessment.reasons)

    # =========================================================================
    # Phase 4: LOW Rule Tests & UNKNOWN NEVER LOWERS PRIORITY
    # =========================================================================

    def test_water_receded_fully_verified_safe_triggers_low(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_level_trend="receded",
            water_depth_cm=0.0,
            trapped_status=False,
            medical_emergency=False,
            hazards=(),
            relief_needs=(),
            unknown_fields=(),
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.LOW
        assert "water_receded_no_active_threats" in assessment.reasons
        assert assessment.requires_human_review is False

    def test_unknown_never_lowers_priority_unknown_trapped_prevents_low(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        """When trapped_status is unknown, priority cannot be LOW even if water is receded."""
        facts = SeverityFacts(
            water_level_trend="receded",
            water_depth_cm=0.0,
            trapped_status=None,  # UNKNOWN
            medical_emergency=False,
            hazards=(),
        )
        assessment = policy.assess(facts)
        # MUST NOT be LOW!
        assert assessment.priority == PriorityLevel.STANDARD
        assert "unverified_safety_baseline_precludes_low_priority" in assessment.reasons
        assert "trapped_status" in assessment.unknown_fields
        assert assessment.requires_human_review is True

    def test_unknown_never_lowers_priority_unknown_medical_prevents_low(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        """When medical_emergency is unknown, priority cannot be LOW."""
        facts = SeverityFacts(
            water_level_trend="receded",
            water_depth_cm=0.0,
            trapped_status=False,
            medical_emergency=None,  # UNKNOWN
            hazards=(),
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.STANDARD
        assert "unverified_safety_baseline_precludes_low_priority" in assessment.reasons
        assert "medical_emergency" in assessment.unknown_fields

    def test_empty_facts_defaults_to_standard_with_human_review(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        """A report with zero information cannot be assumed safe (LOW) — defaults to STANDARD."""
        facts = SeverityFacts()
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.STANDARD
        assert "unverified_safety_baseline_precludes_low_priority" in assessment.reasons
        assert assessment.requires_human_review is True
        assert len(assessment.unknown_fields) > 0

    # =========================================================================
    # Explanation Completeness & Determinism Tests
    # =========================================================================

    def test_full_decision_explanation_list(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        """Verify that all matching operational factors are accumulated in the reasons tuple."""
        facts = SeverityFacts(
            water_entering_occupied_floor=True,
            medical_emergency=True,
            is_life_threatening_medical=True,
            relief_needs=("food", "clean_water"),
        )
        assessment = policy.assess(facts)
        assert assessment.priority == PriorityLevel.CRITICAL_REVIEW
        assert "critical_medical_emergency" in assessment.reasons
        assert "water_entering_occupied_floor" in assessment.reasons
        assert "relief_need:food" in assessment.reasons
        assert "relief_need:clean_water" in assessment.reasons

    def test_unknown_fields_preserved_transparently(
        self, policy: DeterministicSafetyPriorityPolicy
    ) -> None:
        facts = SeverityFacts(
            water_entering_occupied_floor=True,
            medical_emergency=True,
            unknown_fields=("exact_people_count", "last_contact_time"),
        )
        assessment = policy.assess(facts)
        assert "exact_people_count" in assessment.unknown_fields
        assert "last_contact_time" in assessment.unknown_fields
