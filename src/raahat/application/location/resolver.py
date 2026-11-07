"""Active location disambiguation and question selection engine."""
from __future__ import annotations

import math
import uuid
from typing import Optional, Sequence

from raahat.domain.geospatial.landmark import BoundingBox, Landmark, LandmarkCandidate
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import VerificationStatus
from raahat.infrastructure.database.repositories.landmark import LandmarkRepository

from .models import (
    ClarificationAnswer,
    ClarificationQuestion,
    LocationObservation,
    LocationResolution,
)

DEFAULT_LANDMARK_UNCERTAINTY_M = 150.0
DEFAULT_GPS_UNCERTAINTY_M = 30.0
UNRESOLVED_AREA_UNCERTAINTY_M = 5000.0


def _compute_bounding_box(
    points: Sequence[PointCoordinates],
    padding_deg: float = 0.002,
) -> BoundingBox:
    """Compute geographic bounding box enclosing points with coordinate clamping."""
    if not points:
        return BoundingBox(
            min_latitude=18.5,
            min_longitude=73.8,
            max_latitude=18.6,
            max_longitude=73.9,
        )

    lats = [p.latitude for p in points]
    lons = [p.longitude for p in points]

    return BoundingBox(
        min_latitude=max(-90.0, min(lats) - padding_deg),
        min_longitude=max(-180.0, min(lons) - padding_deg),
        max_latitude=min(90.0, max(lats) + padding_deg),
        max_longitude=min(180.0, max(lons) + padding_deg),
    )


def _compute_entropy(probabilities: Sequence[float]) -> float:
    """Compute Shannon entropy in bits for discrete distribution."""
    h = 0.0
    for p in probabilities:
        if p > 1e-9:
            h -= p * math.log2(p)
    return h


class PostGISGazetteerResolver:
    """LocationResolver combining PostGIS landmark search with active disambiguation."""

    def __init__(
        self,
        landmark_repo: LandmarkRepository,
        default_landmark_uncertainty_m: float = DEFAULT_LANDMARK_UNCERTAINTY_M,
        gps_uncertainty_m: float = DEFAULT_GPS_UNCERTAINTY_M,
    ) -> None:
        self._landmark_repo = landmark_repo
        self._default_uncertainty_m = default_landmark_uncertainty_m
        self._gps_uncertainty_m = gps_uncertainty_m

    async def resolve(self, observation: LocationObservation) -> LocationResolution:
        """Resolve location observation into hypotheses, uncertainty bounding, and questions."""
        incident_id = observation.incident_id

        # ------------------------------------------------------------------
        # 1. Direct coordinates (GPS / WhatsApp pin) provided
        # ------------------------------------------------------------------
        if observation.coordinates is not None:
            coords = observation.coordinates
            nearby = self._landmark_repo.find_within_radius(
                center=coords,
                radius_m=300.0,
                kind_filter=None,
                max_results=1,
            )
            resolved_lm: Optional[Landmark] = nearby[0].landmark if nearby else None
            label = (
                f"GPS Coordinates (near {resolved_lm.name})"
                if resolved_lm is not None
                else "GPS Coordinates"
            )

            hyp = LocationHypothesis(
                incident_id=incident_id,
                coordinates=coords,
                candidate_label=label,
                probability=None,  # Explicitly uncalibrated per spec
                uncertainty_radius_m=self._gps_uncertainty_m,
                verification_status=VerificationStatus.UNVERIFIED,
            )
            bbox = _compute_bounding_box([coords], padding_deg=0.001)

            return LocationResolution(
                hypotheses=[hyp],
                bounding_box=bbox,
                uncertainty_radius_m=self._gps_uncertainty_m,
                clarification_question=None,
                resolved_landmark=resolved_lm,
            )

        # ------------------------------------------------------------------
        # 2. Textual landmark search
        # ------------------------------------------------------------------
        raw_text = (observation.raw_text or "").strip()
        candidates: list[LandmarkCandidate] = []
        if raw_text:
            candidates = self._landmark_repo.search_by_text(
                query=raw_text,
                bounding_box=observation.bounding_box,
                max_results=10,
                similarity_threshold=0.25,
            )

        # Apply ward filter or boost if specified
        if observation.ward_code and candidates:
            ward_lower = observation.ward_code.lower()
            matching_ward = [
                c
                for c in candidates
                if str(c.landmark.metadata.get("ward", "")).lower() == ward_lower
            ]
            if matching_ward:
                candidates = matching_ward

        # ------------------------------------------------------------------
        # 3. Evaluate prior answers
        # ------------------------------------------------------------------
        relative_direction_answer: Optional[str] = None
        for answer in observation.answers:
            # Check for disambiguation selection
            candidates = self._filter_by_answer(candidates, answer)
            # Check for relative direction response
            direction = self._extract_direction(answer)
            if direction:
                relative_direction_answer = direction

        # ------------------------------------------------------------------
        # 4. Handle Case: Zero candidates
        # ------------------------------------------------------------------
        if not candidates:
            return self._handle_unresolved(observation)

        # ------------------------------------------------------------------
        # 5. Handle Case: Single candidate landmark
        # ------------------------------------------------------------------
        if len(candidates) == 1:
            lm = candidates[0].landmark
            if relative_direction_answer:
                # Relative direction is known: narrow uncertainty
                uncertainty = self._default_uncertainty_m / 2.0
                label = f"{lm.name} ({relative_direction_answer})"
                hyp = LocationHypothesis(
                    incident_id=incident_id,
                    coordinates=lm.location,
                    candidate_label=label,
                    probability=None,
                    uncertainty_radius_m=uncertainty,
                    verification_status=VerificationStatus.UNVERIFIED,
                )
                bbox = _compute_bounding_box([lm.location])
                return LocationResolution(
                    hypotheses=[hyp],
                    bounding_box=bbox,
                    uncertainty_radius_m=uncertainty,
                    clarification_question=None,
                    resolved_landmark=lm,
                )

            # Propose relative direction disambiguation question
            hyp = LocationHypothesis(
                incident_id=incident_id,
                coordinates=lm.location,
                candidate_label=lm.name,
                probability=None,
                uncertainty_radius_m=self._default_uncertainty_m,
                verification_status=VerificationStatus.UNVERIFIED,
            )
            bbox = _compute_bounding_box([lm.location])
            question = ClarificationQuestion(
                prompt_text=f"Kya aap {lm.name} ke samne hain ya peeche?",
                question_type="relative_direction",
                options=["Samne (Front)", "Peeche (Behind)", "Paas mein (Nearby)"],
                candidate_landmark_ids=[lm.id],
                expected_information_gain=1.0,
            )
            return LocationResolution(
                hypotheses=[hyp],
                bounding_box=bbox,
                uncertainty_radius_m=self._default_uncertainty_m,
                clarification_question=question,
                resolved_landmark=lm,
            )

        # ------------------------------------------------------------------
        # 6. Handle Case: Multiple candidate landmarks (ambiguity)
        # ------------------------------------------------------------------
        return self._handle_ambiguous_candidates(
            incident_id=incident_id,
            candidates=candidates,
        )

    def _filter_by_answer(
        self,
        candidates: list[LandmarkCandidate],
        answer: ClarificationAnswer,
    ) -> list[LandmarkCandidate]:
        """Filter candidate list if answer selects a specific landmark option."""
        text = (answer.selected_option or answer.text_response or "").lower().strip()
        if not text:
            return candidates

        # 1. Check if answer matches specific distinguishing metadata (ward, kind, or ID)
        matched_meta: list[LandmarkCandidate] = []
        for c in candidates:
            ward = str(c.landmark.metadata.get("ward", "")).lower()
            kind = c.landmark.kind.lower()
            if ward and f"({ward})" in text or (ward and ward in text):
                matched_meta.append(c)
            elif str(c.landmark.id) in text:
                matched_meta.append(c)
            elif kind and f"({kind})" in text:
                matched_meta.append(c)

        if matched_meta:
            return matched_meta

        # 2. Fallback to name matching
        matched = [
            c for c in candidates if c.landmark.name.lower() in text or text in c.landmark.name.lower()
        ]
        return matched if matched else candidates

    def _extract_direction(self, answer: ClarificationAnswer) -> Optional[str]:
        """Extract relative direction (front/behind) from answer text."""
        combined = f"{answer.selected_option or ''} {answer.text_response or ''}".lower()
        if "samne" in combined or "front" in combined or "aage" in combined:
            return "samne"
        if "peeche" in combined or "behind" in combined or "back" in combined:
            return "peeche"
        if "paas" in combined or "near" in combined:
            return "paas mein"
        return None

    def _handle_unresolved(self, observation: LocationObservation) -> LocationResolution:
        """Fallback resolution when no landmarks match."""
        incident_id = observation.incident_id
        if observation.bounding_box is not None:
            bbox = observation.bounding_box
            center = PointCoordinates(
                latitude=(bbox.min_latitude + bbox.max_latitude) / 2.0,
                longitude=(bbox.min_longitude + bbox.max_longitude) / 2.0,
            )
            radius = center.distance_to(
                PointCoordinates(latitude=bbox.max_latitude, longitude=bbox.max_longitude)
            )
            hyp = LocationHypothesis(
                incident_id=incident_id,
                coordinates=center,
                candidate_label="Disaster Zone Estimate (No Landmark Match)",
                probability=None,
                uncertainty_radius_m=radius,
                verification_status=VerificationStatus.UNVERIFIED,
            )
            question = ClarificationQuestion(
                prompt_text="Aap kahan phanse hain? Kripya aas paas ka koi bada landmark (mandir, school, pul, chowk) batayein.",
                question_type="general",
                options=[],
                candidate_landmark_ids=[],
                expected_information_gain=None,
            )
            return LocationResolution(
                hypotheses=[hyp],
                bounding_box=bbox,
                uncertainty_radius_m=radius,
                clarification_question=question,
                resolved_landmark=None,
            )

        # Default fallback without bounding box
        default_center = PointCoordinates(latitude=18.5204, longitude=73.8567)
        hyp = LocationHypothesis(
            incident_id=incident_id,
            coordinates=default_center,
            candidate_label="Unresolved Location (Missing Landmark)",
            probability=None,
            uncertainty_radius_m=UNRESOLVED_AREA_UNCERTAINTY_M,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        question = ClarificationQuestion(
            prompt_text="Aapka sthan confirm nahi ho paaya. Kripya apna ward number ya aas paas ka landmark batayein.",
            question_type="general",
            options=[],
            candidate_landmark_ids=[],
            expected_information_gain=None,
        )
        bbox = _compute_bounding_box([default_center], padding_deg=0.05)
        return LocationResolution(
            hypotheses=[hyp],
            bounding_box=bbox,
            uncertainty_radius_m=UNRESOLVED_AREA_UNCERTAINTY_M,
            clarification_question=question,
            resolved_landmark=None,
        )

    def _handle_ambiguous_candidates(
        self,
        incident_id: uuid.UUID,
        candidates: list[LandmarkCandidate],
    ) -> LocationResolution:
        """Calculate spatial spread, EIG, and select the optimal disambiguation question."""
        points = [c.landmark.location for c in candidates]
        bbox = _compute_bounding_box(points)

        # Compute centroid and spread radius
        avg_lat = sum(p.latitude for p in points) / len(points)
        avg_lon = sum(p.longitude for p in points) / len(points)
        centroid = PointCoordinates(latitude=avg_lat, longitude=avg_lon)
        max_dist = max(centroid.distance_to(p) for p in points)
        uncertainty_radius = max_dist + self._default_uncertainty_m

        # Build hypotheses for top candidates
        hypotheses = [
            LocationHypothesis(
                incident_id=incident_id,
                coordinates=c.landmark.location,
                candidate_label=f"{c.landmark.name} ({c.landmark.kind})",
                probability=None,  # NEVER fabricate confidence!
                uncertainty_radius_m=self._default_uncertainty_m,
                verification_status=VerificationStatus.UNVERIFIED,
            )
            for c in candidates[:5]
        ]

        # Calculate EIG between the top two candidates
        top1, top2 = candidates[0], candidates[1]
        s1 = max(top1.score, 0.01)
        s2 = max(top2.score, 0.01)
        p1 = s1 / (s1 + s2)
        p2 = s2 / (s1 + s2)
        eig = _compute_entropy([p1, p2])

        # Distinguish top candidates by ward, kind, or index
        def _label(c: LandmarkCandidate) -> str:
            extra = c.landmark.metadata.get("ward") or c.landmark.kind
            return f"{c.landmark.name} ({extra})"

        opt1 = _label(top1)
        opt2 = _label(top2)
        question = ClarificationQuestion(
            prompt_text=f"Kya aap {opt1} ke paas hain ya {opt2} ke paas?",
            question_type="disambiguation",
            options=[opt1, opt2],
            candidate_landmark_ids=[top1.landmark.id, top2.landmark.id],
            expected_information_gain=round(eig, 3),
        )

        return LocationResolution(
            hypotheses=hypotheses,
            bounding_box=bbox,
            uncertainty_radius_m=uncertainty_radius,
            clarification_question=question,
            resolved_landmark=None,
        )
