"""Contradiction and corroboration detection across multi-report evidence claims."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol, runtime_checkable

from raahat.domain.evidence.evidence import Contradiction, Corroboration, EvidenceItem

logger = logging.getLogger(__name__)

# Mutually exclusive trend pairs
_TREND_CONTRADICTIONS: set[frozenset[str]] = {
    frozenset({"rising", "receded"}),
    frozenset({"rising", "falling"}),
    frozenset({"stable", "receded"}),
}


@runtime_checkable
class ContradictionDetector(Protocol):
    """Protocol for detecting factual contradictions and corroborations across evidence items."""

    def detect_contradictions(self, items: list[EvidenceItem]) -> list[Contradiction]:
        """Detect contradictory claims across evidence items from distinct reports."""
        ...

    def detect_corroborations(self, items: list[EvidenceItem]) -> list[Corroboration]:
        """Identify corroborating claims across independent reports."""
        ...


class RuleBasedContradictionDetector:
    """Deterministic, policy-driven conflict detector evaluating cross-report consistency."""

    def detect_contradictions(self, items: list[EvidenceItem]) -> list[Contradiction]:
        """Evaluate pairs of evidence items for factual incompatibility."""
        contradictions: list[Contradiction] = []
        # De-duplicate on (report_a_id, report_b_id, attribute) to avoid multiple
        # Contradiction records when the same two reports each contribute multiple
        # evidence items for the same attribute.
        seen_report_pairs: set[tuple[uuid.UUID, uuid.UUID, str]] = set()

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                item_a = items[i]
                item_b = items[j]

                # A single report cannot contradict itself across distinct reports
                if item_a.report_id == item_b.report_id:
                    continue

                # Must share the same attribute to contradict
                if item_a.attribute != item_b.attribute:
                    continue

                pair_key = (
                    min(item_a.report_id, item_b.report_id),
                    max(item_a.report_id, item_b.report_id),
                    item_a.attribute,
                )
                if pair_key in seen_report_pairs:
                    continue

                conflict = self._evaluate_conflict(item_a, item_b)
                if conflict is not None:
                    seen_report_pairs.add(pair_key)
                    contradictions.append(conflict)

        return contradictions

    def detect_corroborations(self, items: list[EvidenceItem]) -> list[Corroboration]:
        """Group matching evidence items from distinct reports into corroboration records."""
        groups: dict[tuple[str, str, Any], list[EvidenceItem]] = {}
        for item in items:
            # Value must be hashable or string-convertible for grouping
            val_key = self._hashable_val(item.value)
            key = (item.subject_type, item.attribute, val_key)
            groups.setdefault(key, []).append(item)

        corroborations: list[Corroboration] = []
        for (subject_type, attribute, _), group_items in groups.items():
            # Check for multiple distinct reports supporting this exact claim
            distinct_reports = {it.report_id: it for it in group_items}
            if len(distinct_reports) >= 2:
                rep_items = list(distinct_reports.values())
                corroborations.append(
                    Corroboration(
                        attribute=attribute,
                        subject_type=subject_type,
                        evidence_item_ids=tuple(it.id for it in rep_items),
                        report_ids=tuple(it.report_id for it in rep_items),
                        value=rep_items[0].value,
                        agreement_count=len(distinct_reports),
                    )
                )

        return corroborations

    def _evaluate_conflict(
        self,
        item_a: EvidenceItem,
        item_b: EvidenceItem,
    ) -> Contradiction | None:
        attr = item_a.attribute
        val_a = item_a.value
        val_b = item_b.value

        # 1. Water level trend conflict
        if attr == "water_level_trend":
            trend_pair = frozenset({str(val_a).lower(), str(val_b).lower()})
            if trend_pair in _TREND_CONTRADICTIONS:
                severity = "high" if "rising" in trend_pair else "medium"
                return self._make_contradiction(
                    item_a=item_a,
                    item_b=item_b,
                    conflict_type="trend_conflict",
                    severity=severity,
                    description=(
                        f"Conflicting water level trend: Report {item_a.report_id} claims '{val_a}' "
                        f"while Report {item_b.report_id} claims '{val_b}'"
                    ),
                )

        # 2. Headcount divergence
        if attr == "people_count":
            try:
                cnt_a = int(val_a)
                cnt_b = int(val_b)
                if cnt_a != cnt_b:
                    diff = abs(cnt_a - cnt_b)
                    ratio = max(cnt_a, cnt_b) / max(min(cnt_a, cnt_b), 1)
                    severity = "high" if diff >= 3 or ratio >= 2.0 else "medium"
                    return self._make_contradiction(
                        item_a=item_a,
                        item_b=item_b,
                        conflict_type="headcount_divergence",
                        severity=severity,
                        description=(
                            f"Varying headcounts: Report {item_a.report_id} claims {cnt_a} people "
                            f"while Report {item_b.report_id} claims {cnt_b} people (difference: {diff})"
                        ),
                    )
            except (ValueError, TypeError):
                pass

        # 3. Boolean conflicts (trapped_status, medical_emergency)
        if attr in ("trapped_status", "medical_emergency") and isinstance(val_a, bool) and isinstance(val_b, bool):
            if val_a != val_b:
                return self._make_contradiction(
                    item_a=item_a,
                    item_b=item_b,
                    conflict_type="boolean_conflict",
                    severity="high",
                    description=(
                        f"Contradictory {attr}: Report {item_a.report_id} claims {val_a} "
                        f"while Report {item_b.report_id} claims {val_b}"
                    ),
                )

        # 4. Water depth discrepancy
        if attr == "water_depth_cm":
            try:
                depth_a = float(val_a)
                depth_b = float(val_b)
                depth_diff = abs(depth_a - depth_b)
                if depth_diff >= 50.0:
                    severity = "high" if depth_diff >= 100.0 else "medium"
                    return self._make_contradiction(
                        item_a=item_a,
                        item_b=item_b,
                        conflict_type="numeric_divergence",
                        severity=severity,
                        description=(
                            f"Discrepant water depth: Report {item_a.report_id} claims {depth_a}cm "
                            f"while Report {item_b.report_id} claims {depth_b}cm (discrepancy: {depth_diff}cm)"
                        ),
                    )
            except (ValueError, TypeError):
                pass

        # 5. Location landmark divergence
        if attr == "landmark_mention":
            str_a = str(val_a).strip().lower()
            str_b = str(val_b).strip().lower()
            if str_a and str_b and str_a != str_b and str_a not in str_b and str_b not in str_a:
                return self._make_contradiction(
                    item_a=item_a,
                    item_b=item_b,
                    conflict_type="location_divergence",
                    severity="medium",
                    description=(
                        f"Discrepant landmark mentions: Report {item_a.report_id} mentions '{val_a}' "
                        f"while Report {item_b.report_id} mentions '{val_b}'"
                    ),
                )

        return None

    def _make_contradiction(
        self,
        item_a: EvidenceItem,
        item_b: EvidenceItem,
        conflict_type: str,
        severity: str,
        description: str,
    ) -> Contradiction:
        # Canonical order by report_id
        ordered = sorted([item_a, item_b], key=lambda x: str(x.report_id))
        first, second = ordered[0], ordered[1]

        return Contradiction(
            attribute=first.attribute,
            subject_type=first.subject_type,
            evidence_item_ids=(first.id, second.id),
            report_ids=(first.report_id, second.report_id),
            conflict_type=conflict_type,
            severity=severity,
            description=description,
            values={
                str(first.report_id): first.value,
                str(second.report_id): second.value,
            },
        )

    def _hashable_val(self, val: Any) -> Any:
        if isinstance(val, (dict, list, set)):
            return str(sorted(val.items())) if isinstance(val, dict) else str(sorted(val))
        return val

