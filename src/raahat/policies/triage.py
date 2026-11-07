"""Deterministic, explainable safety triage policy adhering to 'Unknown never lowers priority'."""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from raahat.domain.shared.enums import PriorityLevel
from raahat.domain.triage.assessment import PriorityAssessment
from raahat.domain.triage.facts import SeverityFacts

logger = logging.getLogger(__name__)

# Acute life-safety hazard keywords
ACUTE_HAZARD_KEYWORDS: tuple[str, ...] = (
    "electrical",
    "power_line",
    "live_wire",
    "gas_leak",
    "collapse",
    "structural_collapse",
    "landslide",
    "explosion",
    "fire",
)


@runtime_checkable
class PriorityPolicy(Protocol):
    """Protocol for calculating explainable priority assessments from severity facts."""

    def assess(self, facts: SeverityFacts) -> PriorityAssessment:
        """Deterministically assess operational priority based on explicit safety rules."""
        ...


class DeterministicSafetyPriorityPolicy:
    """Calculates operational rescue priority using explicit, deterministic safety rules.

    Guarantees:
    1. Zero arbitrary floating-point weights (all logic is rule-based and explainable).
    2. 'Unknown never lowers priority' rule: unverified fields never reduce urgency.
    3. Missing information remains explicitly tagged in unknown_fields.
    4. Full decision explanation: produces comprehensive list of triggered reasons.
    5. Always requires human review for high-risk or uncertain situations.
    """

    def assess(self, facts: SeverityFacts) -> PriorityAssessment:
        reasons: list[str] = []
        unknown_fields: list[str] = list(facts.unknown_fields)

        # -------------------------------------------------------------
        # Phase 1: CRITICAL_REVIEW Triggers (Life-Threatening Emergency)
        # -------------------------------------------------------------
        critical_reasons: list[str] = []

        # 1.1 Critical / Life-threatening Medical Emergency
        if facts.is_life_threatening_medical:
            critical_reasons.append("critical_medical_emergency")
        elif facts.medical_emergency and (
            facts.trapped_status is True
            or facts.water_level_trend == "rising"
            or facts.vulnerable_present is True
            or (facts.water_depth_cm is not None and facts.water_depth_cm >= 100)
        ):
            critical_reasons.append("medical_need_with_trapped_or_rising_water")

        # 1.2 Water Entering Occupied Floor
        if facts.water_entering_occupied_floor is True:
            critical_reasons.append("water_entering_occupied_floor")
        elif facts.current_floor == "ground" and facts.water_depth_cm is not None and facts.water_depth_cm >= 100:
            critical_reasons.append("ground_floor_submerged_exceeds_threshold")

        # 1.3 Trapped Occupants with Rising Water
        if facts.trapped_status is True and facts.water_level_trend == "rising":
            critical_reasons.append("rising_water_with_trapped_occupants")

        # 1.4 Acute Life Safety Hazards
        for h in facts.hazards:
            h_lower = h.lower()
            if any(k in h_lower for k in ACUTE_HAZARD_KEYWORDS):
                critical_reasons.append(f"acute_hazard:{h}")

        # 1.5 High Headcount Trapped
        if facts.trapped_status is True and facts.people_count is not None and facts.people_count >= 5:
            critical_reasons.append("high_headcount_trapped")

        # 1.6 Vulnerable Persons Trapped
        if facts.trapped_status is True and facts.vulnerable_present is True:
            critical_reasons.append("vulnerable_persons_trapped")

        # 1.7 Life-Safety Contradictions Detected in Evidence
        if facts.has_contradictions:
            critical_reasons.append("evidence_contradiction_detected")

        # 1.8 Rising Deep Flood with Unknown Occupancy ('Unknown never lowers priority')
        if (
            facts.water_level_trend == "rising"
            and facts.water_depth_cm is not None
            and facts.water_depth_cm >= 150
            and facts.trapped_status is None
        ):
            critical_reasons.append("deep_rising_flood_with_unknown_occupants")

        # -------------------------------------------------------------
        # Phase 2: URGENT Triggers (High Urgency / Severe Condition)
        # -------------------------------------------------------------
        urgent_reasons: list[str] = []

        # 2.1 Occupants Trapped
        if facts.trapped_status is True and "rising_water_with_trapped_occupants" not in critical_reasons:
            urgent_reasons.append("occupants_trapped")

        # 2.2 Medical Need Reported
        if facts.medical_emergency is True and not critical_reasons:
            urgent_reasons.append("medical_need_reported")

        # 2.3 Rising Water Level
        if facts.water_level_trend == "rising" and "rising_water_with_trapped_occupants" not in critical_reasons:
            urgent_reasons.append("rising_water_level")

        # 2.4 Significant Water Depth (>= 1 meter)
        if facts.water_depth_cm is not None and facts.water_depth_cm >= 100:
            if "ground_floor_submerged_exceeds_threshold" not in critical_reasons:
                urgent_reasons.append("significant_water_depth")

        # 2.5 Vulnerable Persons in Hazard Area
        if facts.vulnerable_present is True and (
            (facts.water_depth_cm is not None and facts.water_depth_cm > 0)
            or facts.water_level_trend in ("rising", "stable")
        ):
            if "vulnerable_persons_trapped" not in critical_reasons:
                urgent_reasons.append("vulnerable_persons_in_hazard_area")

        # 2.6 Active Hazards
        if len(facts.hazards) > 0:
            non_acute_hazards = [
                h for h in facts.hazards
                if not any(k in h.lower() for k in ACUTE_HAZARD_KEYWORDS)
            ]
            for h in non_acute_hazards:
                urgent_reasons.append(f"hazard_reported:{h}")

        # 2.7 Water Depth with Unknown Occupancy ('Unknown never lowers priority')
        if (
            facts.water_depth_cm is not None
            and facts.water_depth_cm >= 60
            and facts.trapped_status is None
        ):
            urgent_reasons.append("water_depth_with_unverified_occupant_safety")

        # 2.8 Rising Water with Unknown Occupancy ('Unknown never lowers priority')
        if facts.water_level_trend == "rising" and facts.trapped_status is None:
            if "deep_rising_flood_with_unknown_occupants" not in critical_reasons:
                urgent_reasons.append("rising_water_with_unknown_occupancy")

        # -------------------------------------------------------------
        # Phase 3: STANDARD Triggers (Moderate Assistance / Property / Baseline)
        # -------------------------------------------------------------
        standard_reasons: list[str] = []

        # 3.1 Shallow or Stable Water
        if (facts.water_depth_cm is not None and facts.water_depth_cm > 0) or facts.water_level_trend in ("stable", "falling"):
            if not critical_reasons and not urgent_reasons:
                standard_reasons.append("shallow_or_stable_water")

        # 3.2 Relief Needs Reported
        if len(facts.relief_needs) > 0:
            for need in facts.relief_needs:
                standard_reasons.append(f"relief_need:{need}")

        # 3.3 Vulnerable Persons (Monitoring)
        if facts.vulnerable_present is True and not critical_reasons and not urgent_reasons:
            standard_reasons.append("vulnerable_persons_require_monitoring")

        # 3.4 Uncertainty Baseline Preservation ('Unknown never lowers priority')
        # If critical life-safety fields are unknown, it cannot be LOW!
        critical_unknowns = {"trapped_status", "medical_emergency", "water_level_trend"}
        has_critical_unknowns = any(k in facts.unknown_fields for k in critical_unknowns)
        if has_critical_unknowns and not critical_reasons and not urgent_reasons:
            standard_reasons.append("unverified_safety_baseline_precludes_low_priority")

        # -------------------------------------------------------------
        # Resolution & Final Assessment
        # -------------------------------------------------------------
        if critical_reasons:
            reasons = critical_reasons + urgent_reasons + standard_reasons
            return PriorityAssessment(
                priority=PriorityLevel.CRITICAL_REVIEW,
                reasons=tuple(reasons),
                unknown_fields=tuple(unknown_fields),
                requires_human_review=True,
            )

        if urgent_reasons:
            reasons = urgent_reasons + standard_reasons
            return PriorityAssessment(
                priority=PriorityLevel.URGENT,
                reasons=tuple(reasons),
                unknown_fields=tuple(unknown_fields),
                requires_human_review=True,
            )

        if standard_reasons:
            reasons = standard_reasons
            return PriorityAssessment(
                priority=PriorityLevel.STANDARD,
                reasons=tuple(reasons),
                unknown_fields=tuple(unknown_fields),
                requires_human_review=True,
            )

        # -------------------------------------------------------------
        # Phase 4: LOW (Explicitly Verified Safe / Resolved / Receded)
        # -------------------------------------------------------------
        reasons = ["water_receded_no_active_threats"]
        return PriorityAssessment(
            priority=PriorityLevel.LOW,
            reasons=tuple(reasons),
            unknown_fields=tuple(unknown_fields),
            requires_human_review=False,
        )
