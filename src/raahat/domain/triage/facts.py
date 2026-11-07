"""Severity facts domain model with explicit uncertainty preservation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SeverityFacts(BaseModel):
    """Normalized operational severity facts extracted from multi-source evidence.

    Explicitly preserves unknown fields: missing or unverified fields are never coerced
    to false or negative observations, strictly enforcing 'unknown never lowers priority'.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Environmental & flood observations
    water_level_trend: Optional[str] = None  # "rising", "falling", "stable", "receded"
    water_depth_cm: Optional[float] = None
    water_entering_occupied_floor: Optional[bool] = None
    current_floor: Optional[str] = None  # "ground", "first", "second", "roof", etc.

    # Human presence & medical observations
    people_count: Optional[int] = None
    trapped_status: Optional[bool] = None
    medical_emergency: Optional[bool] = None
    is_life_threatening_medical: Optional[bool] = None
    vulnerable_present: Optional[bool] = None
    vulnerable_details: tuple[str, ...] = Field(default_factory=tuple)

    # Hazards & relief needs
    hazards: tuple[str, ...] = Field(default_factory=tuple)
    relief_needs: tuple[str, ...] = Field(default_factory=tuple)

    # Evidence provenance & conflict indicators
    has_contradictions: bool = False
    contradiction_reasons: tuple[str, ...] = Field(default_factory=tuple)
    unverified_reports_count: int = 0
    total_reports_count: int = 0
    last_contact_time: Optional[datetime] = None

    # Explicit uncertainty tracking
    unknown_fields: tuple[str, ...] = Field(default_factory=tuple)
    raw_observations: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def populate_unknown_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data_dict = dict(data)
            unknowns = list(data_dict.get("unknown_fields") or [])

            critical_checks = [
                ("water_level_trend", data_dict.get("water_level_trend")),
                ("water_depth_cm", data_dict.get("water_depth_cm")),
                ("water_entering_occupied_floor", data_dict.get("water_entering_occupied_floor")),
                ("current_floor", data_dict.get("current_floor")),
                ("exact_people_count", data_dict.get("people_count")),
                ("trapped_status", data_dict.get("trapped_status")),
                ("medical_emergency", data_dict.get("medical_emergency")),
                ("vulnerable_present", data_dict.get("vulnerable_present")),
                ("last_contact_time", data_dict.get("last_contact_time")),
            ]
            for name, val in critical_checks:
                if val is None and name not in unknowns:
                    unknowns.append(name)
            data_dict["unknown_fields"] = tuple(unknowns)
            return data_dict
        return data
