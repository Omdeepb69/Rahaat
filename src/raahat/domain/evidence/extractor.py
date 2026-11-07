"""Report evidence extraction and decomposition into atomic claims with spans."""
from __future__ import annotations

import logging
import re
from typing import Any, Optional, Protocol, runtime_checkable

from raahat.domain.evidence.evidence import EvidenceItem, EvidenceSpan
from raahat.domain.reports.report import Report
from raahat.domain.shared.enums import VerificationStatus

logger = logging.getLogger(__name__)

# Canonical trend normalizations
_TREND_MAP: dict[str, str] = {
    "rising": "rising",
    "increasing": "rising",
    "up": "rising",
    "badh raha": "rising",
    "badh raha hai": "rising",
    "paani badh": "rising",
    "falling": "falling",
    "decreasing": "falling",
    "down": "falling",
    "ghat raha": "falling",
    "ghat raha hai": "falling",
    "receded": "receded",
    "cleared": "receded",
    "dry": "receded",
    "utar gaya": "receded",
    "stable": "stable",
    "same": "stable",
    "ruka hua": "stable",
}


# Canonical concept keywords for audio turn matching
_CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "water_level_trend": ["water", "paani", "flood", "badh", "ghat", "level", "trend", "rising", "falling", "receded"],
    "water_depth_cm": ["depth", "gehra", "water", "paani", "feet", "cm", "inch", "level"],
    "people_count": ["people", "log", "headcount", "person", "trapped", "aadmi", "bacche", "jan"],
    "trapped_status": ["trapped", "phas", "fase", "stranded", "bachao", "safe"],
    "medical_emergency": ["medical", "doctor", "injury", "injured", "chot", "dawai", "ambulance", "bimar"],
    "landmark_mention": ["mandir", "masjid", "school", "station", "near", "pass", "chowk", "road"],
}


@runtime_checkable
class ReportEvidenceExtractor(Protocol):
    """Protocol for extracting evidence items and spans from reports."""

    def extract(self, report: Report) -> list[EvidenceItem]:
        """Extract atomic evidence claims from a raw report."""
        ...


class StructuredEvidenceExtractor:
    """Decomposes reports from any channel into atomic EvidenceItems with source spans."""

    def extract(self, report: Report) -> list[EvidenceItem]:
        """Decompose report into atomic evidence items with preserved source spans."""
        payload = report.raw_payload or {}
        items: list[EvidenceItem] = []
        observed_at = report.client_created_at or report.received_at

        # Flatten nested 'parsed' or 'extracted' sub-dictionaries if present
        flattened = self._flatten_payload(payload)

        # 1. Headcount / People count
        people_count = self._extract_int(
            flattened,
            ["people_count", "headcount", "total_people", "trapped_count", "head_count"],
        )
        if people_count is not None:
            span = self._find_span(
                payload,
                key="people_count",
                val_repr=str(people_count["value"]),
                field_name=people_count["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="household",
                    attribute="people_count",
                    value=people_count["value"],
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 2. Water level trend
        trend = self._extract_trend(
            flattened,
            ["water_level_trend", "water_level", "flood_level", "flood_trend"],
        )
        if trend is not None:
            span = self._find_span(
                payload,
                key="water_level_trend",
                val_repr=str(trend["raw_value"]),
                field_name=trend["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="environment",
                    attribute="water_level_trend",
                    value=trend["value"],
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 3. Water depth in cm
        water_depth = self._extract_float(
            flattened,
            ["water_depth_cm", "flood_depth_cm", "water_depth", "depth_cm"],
        )
        if water_depth is not None:
            span = self._find_span(
                payload,
                key="water_depth_cm",
                val_repr=str(water_depth["value"]),
                field_name=water_depth["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="environment",
                    attribute="water_depth_cm",
                    value=water_depth["value"],
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 4. Trapped status
        trapped = self._extract_bool(
            flattened,
            ["trapped_status", "trapped", "is_trapped", "stranded"],
        )
        if trapped is not None:
            span = self._find_span(
                payload,
                key="trapped_status",
                val_repr=str(trapped["value"]),
                field_name=trapped["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="household",
                    attribute="trapped_status",
                    value=trapped["value"],
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 5. Medical emergency
        medical = self._extract_bool(
            flattened,
            ["medical_emergency", "medical_need", "has_injury", "urgent_rescue"],
        )
        if medical is not None:
            span = self._find_span(
                payload,
                key="medical_emergency",
                val_repr=str(medical["value"]),
                field_name=medical["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="household",
                    attribute="medical_emergency",
                    value=medical["value"],
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 6. Landmark / location mention
        landmark = self._extract_str(
            flattened,
            ["location", "location_text", "landmark", "address", "landmark_mention"],
        )
        if landmark is not None and landmark["value"].strip():
            span = self._find_span(
                payload,
                key="landmark_mention",
                val_repr=landmark["value"],
                field_name=landmark["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="location",
                    attribute="landmark_mention",
                    value=landmark["value"].strip(),
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        # 7. Relief needs
        needs = flattened.get("needs") or flattened.get("relief_needs")
        if needs is not None:
            need_list = needs if isinstance(needs, list) else [str(needs)]
            for need in need_list:
                need_str = str(need).strip().lower()
                if not need_str:
                    continue
                span = self._find_span(
                    payload,
                    key="relief_need",
                    val_repr=need_str,
                    field_name="needs",
                )
                items.append(
                    EvidenceItem(
                        report_id=report.id,
                        subject_type="need",
                        attribute="relief_need",
                        value=need_str,
                        observed_at=observed_at,
                        verification_status=VerificationStatus.UNVERIFIED,
                        spans=(span,),
                    )
                )

        # 8. Hazards
        hazard = self._extract_str(flattened, ["hazard", "hazards"])
        if hazard is not None and hazard["value"].strip():
            span = self._find_span(
                payload,
                key="hazard",
                val_repr=hazard["value"],
                field_name=hazard["field"],
            )
            items.append(
                EvidenceItem(
                    report_id=report.id,
                    subject_type="environment",
                    attribute="hazard",
                    value=hazard["value"].strip(),
                    observed_at=observed_at,
                    verification_status=VerificationStatus.UNVERIFIED,
                    spans=(span,),
                )
            )

        return items

    def _flatten_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Flatten direct and nested 'parsed', 'extracted' fields into a unified lookup."""
        result: dict[str, Any] = {}
        for k, v in payload.items():
            if k in ("parsed", "extracted") and isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    result[sub_k] = sub_v
            else:
                result[k] = v
        return result

    def _extract_int(self, data: dict[str, Any], candidate_keys: list[str]) -> Optional[dict[str, Any]]:
        for k in candidate_keys:
            if k in data and data[k] is not None:
                try:
                    val = int(data[k])
                    return {"field": k, "value": val}
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_float(self, data: dict[str, Any], candidate_keys: list[str]) -> Optional[dict[str, Any]]:
        for k in candidate_keys:
            if k in data and data[k] is not None:
                try:
                    val = float(data[k])
                    return {"field": k, "value": val}
                except (ValueError, TypeError):
                    continue
        return None

    def _extract_bool(self, data: dict[str, Any], candidate_keys: list[str]) -> Optional[dict[str, Any]]:
        for k in candidate_keys:
            if k in data and data[k] is not None:
                val = data[k]
                if isinstance(val, bool):
                    return {"field": k, "value": val}
                if isinstance(val, (int, float)):
                    return {"field": k, "value": bool(val)}
                if isinstance(val, str):
                    lower = val.strip().lower()
                    if lower in ("true", "1", "yes", "y", "ha", "haan"):
                        return {"field": k, "value": True}
                    if lower in ("false", "0", "no", "n", "nahi"):
                        return {"field": k, "value": False}
        return None

    def _extract_str(self, data: dict[str, Any], candidate_keys: list[str]) -> Optional[dict[str, Any]]:
        for k in candidate_keys:
            if k in data and data[k] is not None:
                val = str(data[k]).strip()
                if val:
                    return {"field": k, "value": val}
        return None

    def _extract_trend(self, data: dict[str, Any], candidate_keys: list[str]) -> Optional[dict[str, Any]]:
        for k in candidate_keys:
            if k in data and data[k] is not None:
                raw_val = str(data[k]).strip().lower()
                for prefix, canonical in _TREND_MAP.items():
                    if prefix in raw_val:
                        return {"field": k, "value": canonical, "raw_value": data[k]}
        return None

    def _find_span(
        self,
        payload: dict[str, Any],
        key: str,
        val_repr: str,
        field_name: str,
    ) -> EvidenceSpan:
        """Construct an EvidenceSpan linking back to exact field, text, and audio turns."""
        turns = payload.get("turns")
        reference: dict[str, Any] = {"source_field": field_name}

        # Check for turn-based audio timestamps (e.g. from IVR calls)
        if isinstance(turns, list):
            keywords = _CONCEPT_KEYWORDS.get(key, []) + re.split(r"\s+", key.replace("_", " "))
            for turn in turns:
                if isinstance(turn, dict):
                    turn_text = str(turn.get("text", "")).lower()
                    if val_repr.lower() in turn_text or any(token in turn_text for token in keywords if len(token) > 1):
                        reference["turn"] = turn.get("turn")
                        return EvidenceSpan(
                            start_ms=turn.get("start_ms"),
                            end_ms=turn.get("end_ms"),
                            text=turn.get("text"),
                            reference=reference,
                        )

        # Check for raw text / transcript
        transcript = payload.get("transcript") or payload.get("text") or payload.get("message")
        if transcript and isinstance(transcript, str):
            return EvidenceSpan(
                start_ms=None,
                end_ms=None,
                text=transcript,
                reference=reference,
            )

        return EvidenceSpan(
            start_ms=None,
            end_ms=None,
            text=f"{field_name}: {val_repr}",
            reference=reference,
        )
