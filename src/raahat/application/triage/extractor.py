"""Evidence graph fact extractor decomposing and aggregating observations into SeverityFacts."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Sequence

from raahat.domain.evidence.evidence import Contradiction, EvidenceGraph, EvidenceItem
from raahat.domain.shared.enums import VerificationStatus
from raahat.domain.triage.facts import SeverityFacts

logger = logging.getLogger(__name__)

# Medical keywords indicating life-threatening emergency
LIFE_THREATENING_MEDICAL_KEYWORDS: tuple[str, ...] = (
    "unconscious",
    "heart",
    "cardiac",
    "stroke",
    "bleeding",
    "pregnant",
    "labor",
    "dialysis",
    "oxygen",
    "severe_injury",
    "critical",
    "choking",
)

# Vulnerability keywords
VULNERABLE_KEYWORDS: tuple[str, ...] = (
    "elderly",
    "old",
    "infant",
    "baby",
    "children",
    "child",
    "pregnant",
    "disabled",
    "handicapped",
    "wheelchair",
    "bedridden",
    "dialysis",
)


class EvidenceGraphFactExtractor:
    """Extracts normalized SeverityFacts from an EvidenceGraph or collection of EvidenceItems.

    Adheres strictly to uncertainty preservation: missing observations are never defaulted
    to safe values, but instead populated as None and tracked in unknown_fields.
    """

    def extract_from_graph(self, graph: EvidenceGraph) -> SeverityFacts:
        """Extract SeverityFacts from an EvidenceGraph."""
        return self.extract_from_evidence(
            evidence_items=graph.evidence_items,
            contradictions=graph.contradictions,
            total_reports=len(graph.report_ids),
        )

    def extract_from_evidence(
        self,
        evidence_items: Sequence[EvidenceItem],
        contradictions: Sequence[Contradiction] = (),
        total_reports: int = 0,
        unverified_reports_count: int = 0,
    ) -> SeverityFacts:
        """Aggregate atomic claims into an operational SeverityFacts model."""
        water_level_trend: Optional[str] = None
        water_depth_cm: Optional[float] = None
        water_entering_occupied_floor: Optional[bool] = None
        current_floor: Optional[str] = None
        people_count: Optional[int] = None
        trapped_status: Optional[bool] = None
        medical_emergency: Optional[bool] = None
        is_life_threatening_medical: Optional[bool] = None
        vulnerable_present: Optional[bool] = None
        vulnerable_details: list[str] = []
        hazards: list[str] = []
        relief_needs: list[str] = []
        last_contact_time: Optional[datetime] = None
        raw_observations: dict[str, Any] = {}

        trend_observations: list[str] = []
        depth_observations: list[float] = []
        count_observations: list[int] = []
        trapped_observations: list[bool] = []
        medical_observations: list[bool] = []

        unverified_items = 0

        for item in evidence_items:
            if item.verification_status == VerificationStatus.UNVERIFIED:
                unverified_items += 1

            if item.observed_at is not None:
                if last_contact_time is None or item.observed_at > last_contact_time:
                    last_contact_time = item.observed_at

            attr = item.attribute
            val = item.value

            # 1. Water level trend
            if attr == "water_level_trend" and val:
                t_str = str(val).lower().strip()
                trend_observations.append(t_str)

            # 2. Water depth in cm
            elif attr in ("water_depth_cm", "flood_depth_cm") and val is not None:
                try:
                    depth_observations.append(float(val))
                except (ValueError, TypeError):
                    pass

            # 3. Water entering occupied floor
            elif attr in ("water_entering_occupied_floor", "water_entered_floor"):
                if isinstance(val, bool):
                    if val is True:
                        water_entering_occupied_floor = True
                    elif water_entering_occupied_floor is None:
                        water_entering_occupied_floor = False

            # 4. Current floor
            elif attr in ("current_floor", "occupied_floor", "floor") and val:
                current_floor = str(val).lower().strip()

            # 5. People count
            elif attr in ("people_count", "headcount", "total_people") and val is not None:
                try:
                    count_observations.append(int(val))
                except (ValueError, TypeError):
                    pass

            # 6. Trapped status
            elif attr in ("trapped_status", "is_trapped") and val is not None:
                if isinstance(val, bool):
                    trapped_observations.append(val)
                elif isinstance(val, str):
                    trapped_observations.append(val.lower() in ("true", "yes", "trapped", "stranded"))

            # 7. Medical emergency
            elif attr in ("medical_emergency", "medical_need") and val is not None:
                if isinstance(val, bool):
                    medical_observations.append(val)
                elif isinstance(val, str):
                    medical_observations.append(val.lower() in ("true", "yes", "urgent", "emergency"))

                # Check for critical keywords in spans or text
                val_text = str(val).lower()
                for span in item.spans:
                    if span.text:
                        val_text += " " + span.text.lower()
                if any(kw in val_text for kw in LIFE_THREATENING_MEDICAL_KEYWORDS):
                    is_life_threatening_medical = True

            # 8. Vulnerable persons
            elif attr in ("vulnerable_persons", "vulnerable_occupants"):
                vulnerable_present = True
                if isinstance(val, (list, tuple)):
                    for v in val:
                        vulnerable_details.append(str(v).lower())
                elif val:
                    vulnerable_details.append(str(val).lower())

            # 9. Hazards
            elif attr in ("hazard", "hazards") and val:
                h_str = str(val).strip()
                if h_str and h_str not in hazards:
                    hazards.append(h_str)

            # 10. Relief needs
            elif attr in ("relief_need", "need", "needs") and val:
                n_str = str(val).strip().lower()
                if n_str and n_str not in relief_needs:
                    relief_needs.append(n_str)
                # Check if relief need mentions vulnerable persons
                if any(kw in n_str for kw in VULNERABLE_KEYWORDS):
                    vulnerable_present = True
                    if n_str not in vulnerable_details:
                        vulnerable_details.append(n_str)

        # Conservative aggregation rules:
        # 1. Trend: "rising" is life-critical, so if any source reports rising, treat as rising.
        if trend_observations:
            if "rising" in trend_observations:
                water_level_trend = "rising"
            else:
                water_level_trend = trend_observations[-1]

        # 2. Depth: Take worst-case (maximum depth observed)
        if depth_observations:
            water_depth_cm = max(depth_observations)

        # 3. Floor submersion: if ground floor and depth >= 100cm, water enters occupied floor
        if current_floor == "ground" and water_depth_cm is not None and water_depth_cm >= 100:
            water_entering_occupied_floor = True

        # 4. People count: take maximum reported headcount for safety planning
        if count_observations:
            people_count = max(count_observations)

        # 5. Trapped: if any report indicates trapped, treat as trapped
        if trapped_observations:
            water_trapped = any(trapped_observations)
            trapped_status = water_trapped

        # 6. Medical: if any report indicates medical need, treat as True
        if medical_observations:
            medical_emergency = any(medical_observations)

        # Contradictions
        has_contradictions = len(contradictions) > 0
        contradiction_reasons = tuple(
            f"Conflict on {c.attribute}: {c.description}" for c in contradictions
        )

        unverified_cnt = unverified_reports_count or unverified_items

        return SeverityFacts(
            water_level_trend=water_level_trend,
            water_depth_cm=water_depth_cm,
            water_entering_occupied_floor=water_entering_occupied_floor,
            current_floor=current_floor,
            people_count=people_count,
            trapped_status=trapped_status,
            medical_emergency=medical_emergency,
            is_life_threatening_medical=is_life_threatening_medical,
            vulnerable_present=vulnerable_present,
            vulnerable_details=tuple(vulnerable_details),
            hazards=tuple(hazards),
            relief_needs=tuple(relief_needs),
            has_contradictions=has_contradictions,
            contradiction_reasons=contradiction_reasons,
            unverified_reports_count=unverified_cnt,
            total_reports_count=total_reports,
            last_contact_time=last_contact_time,
            raw_observations=raw_observations,
        )
