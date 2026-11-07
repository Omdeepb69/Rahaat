"""Conservative incident resolver enforcing safety thresholds and review routing."""
from __future__ import annotations

from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import IncidentLinkType

from .models import IncidentCandidate, ResolutionDecision, ResolutionDecisionType


class ConservativeIncidentResolver:
    """Enforces conservative thresholds so false merges are avoided and ambiguous matches route to humans."""

    def __init__(
        self,
        auto_link_threshold: float = 0.80,
        review_threshold: float = 0.40,
        min_margin: float = 0.15,
        max_auto_distance_m: float = 150.0,
    ) -> None:
        self.auto_link_threshold = auto_link_threshold
        self.review_threshold = review_threshold
        self.min_margin = min_margin
        self.max_auto_distance_m = max_auto_distance_m

    def evaluate(
        self,
        report: Report,
        candidates: list[IncidentCandidate],
    ) -> ResolutionDecision:
        """Evaluate candidates and decide whether to auto-link, route to review, or create new incident."""
        if not candidates:
            return ResolutionDecision(
                report_id=report.id,
                decision_type=ResolutionDecisionType.CREATE_NEW,
                matched_incident_id=None,
                candidates=[],
                requires_review=False,
                suggested_link_type=None,
                rationale="No candidate incidents found within disaster zone",
            )

        # Filter candidates above review threshold
        valid_candidates = [c for c in candidates if c.score >= self.review_threshold]
        if not valid_candidates:
            return ResolutionDecision(
                report_id=report.id,
                decision_type=ResolutionDecisionType.CREATE_NEW,
                matched_incident_id=None,
                candidates=candidates,
                requires_review=False,
                suggested_link_type=None,
                rationale=f"All candidate incidents scored below review threshold ({self.review_threshold:.2f})",
            )

        top_candidate = valid_candidates[0]

        # 1. Contradiction safety check: zero-tolerance for severe contradictions
        if top_candidate.conflicts:
            return ResolutionDecision(
                report_id=report.id,
                decision_type=ResolutionDecisionType.REQUIRES_REVIEW,
                matched_incident_id=top_candidate.incident_id,
                candidates=candidates,
                requires_review=True,
                suggested_link_type=IncidentLinkType.CONFLICTING,
                rationale=(
                    f"Contradictions detected with candidate incident {top_candidate.incident_id}: "
                    f"{'; '.join(top_candidate.conflicts)}"
                ),
            )

        # 2. Distance safety check: spatial distance must not exceed conservative auto limit
        if (
            top_candidate.spatial_distance_m is not None
            and top_candidate.spatial_distance_m > self.max_auto_distance_m
        ):
            return ResolutionDecision(
                report_id=report.id,
                decision_type=ResolutionDecisionType.REQUIRES_REVIEW,
                matched_incident_id=top_candidate.incident_id,
                candidates=candidates,
                requires_review=True,
                suggested_link_type=top_candidate.suggested_link_type,
                rationale=(
                    f"Spatial distance ({top_candidate.spatial_distance_m:.1f}m) exceeds max auto-link limit "
                    f"({self.max_auto_distance_m:.1f}m); requires dispatcher review"
                ),
            )

        # 3. Confidence threshold check: score must reach auto_link_threshold
        if top_candidate.score < self.auto_link_threshold:
            return ResolutionDecision(
                report_id=report.id,
                decision_type=ResolutionDecisionType.REQUIRES_REVIEW,
                matched_incident_id=top_candidate.incident_id,
                candidates=candidates,
                requires_review=True,
                suggested_link_type=top_candidate.suggested_link_type,
                rationale=(
                    f"Candidate score ({top_candidate.score:.2f}) is in ambiguous range "
                    f"[{self.review_threshold:.2f}, {self.auto_link_threshold:.2f}); requires dispatcher review"
                ),
            )

        # 4. Ambiguity margin check: top candidate must lead runner-up by min_margin
        if len(valid_candidates) > 1:
            runner_up = valid_candidates[1]
            margin = top_candidate.score - runner_up.score
            if margin < self.min_margin:
                return ResolutionDecision(
                    report_id=report.id,
                    decision_type=ResolutionDecisionType.REQUIRES_REVIEW,
                    matched_incident_id=top_candidate.incident_id,
                    candidates=candidates,
                    requires_review=True,
                    suggested_link_type=IncidentLinkType.POSSIBLE_DUPLICATE,
                    rationale=(
                        f"Ambiguous match: margin between top candidates ({top_candidate.score:.2f} vs "
                        f"{runner_up.score:.2f}) is {margin:.2f} (< {self.min_margin:.2f}); requires dispatcher review"
                    ),
                )

        # 5. All conservative criteria satisfied -> safe to auto-link
        return ResolutionDecision(
            report_id=report.id,
            decision_type=ResolutionDecisionType.AUTO_LINK,
            matched_incident_id=top_candidate.incident_id,
            candidates=candidates,
            requires_review=False,
            suggested_link_type=top_candidate.suggested_link_type,
            rationale=(
                f"High-confidence conservative match ({top_candidate.score:.2f}) with incident "
                f"{top_candidate.incident_id}; no contradictions detected"
            ),
        )
