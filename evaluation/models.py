"""Domain and benchmark models for RaahatBench dataset and ground-truth references."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import SourceType


class GroundTruthHousehold(BaseModel):
    """Ground truth details for an individual household within an incident cluster."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    household_id: str
    family_name: str
    people_count: int
    vulnerable_members: list[str] = Field(default_factory=list)
    has_medical_emergency: bool = False
    medical_emergency_details: Optional[str] = None
    floor: int = 1
    location_name: str
    latitude: float
    longitude: float

    @property
    def coordinates(self) -> PointCoordinates:
        return PointCoordinates(latitude=self.latitude, longitude=self.longitude)


class GroundTruthIncident(BaseModel):
    """Authoritative ground-truth incident against which predictions are scored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: uuid.UUID
    incident_code: str
    title: str
    disaster_id: uuid.UUID
    landmark_name: str
    area_name: str
    district: str
    pincode: str
    latitude: float
    longitude: float
    true_severity: str  # critical, urgent, standard, low
    water_depth_cm: float
    water_trend: str  # rising, receding, stable
    trapped_status: str  # trapped_roof, trapped_upper_floor, ground_submerged, none
    total_people: int
    has_medical_emergency: bool
    has_vulnerable_people: bool
    households: list[GroundTruthHousehold] = Field(default_factory=list)
    is_active: bool = True

    @property
    def coordinates(self) -> PointCoordinates:
        return PointCoordinates(latitude=self.latitude, longitude=self.longitude)


class BenchmarkReportRecord(BaseModel):
    """An individual synthetic report within the RaahatBench dataset with ground-truth linkage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: uuid.UUID
    disaster_id: uuid.UUID
    ground_truth_incident_id: uuid.UUID
    ground_truth_household_id: Optional[str] = None
    source_type: SourceType
    source_identity: str
    relationship: str  # direct, relative, volunteer, responder
    language_code: str  # hi, en, ml
    language_mode: str  # hindi, english, code_switched, malayalam
    raw_text: str
    audio_metadata: Optional[dict[str, Any]] = None
    mentioned_landmarks: list[str] = Field(default_factory=list)
    is_location_ambiguous: bool = False
    has_contradiction: bool = False
    contradiction_type: Optional[str] = None
    has_missing_fields: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    is_duplicate: bool = False
    is_offline_sync: bool = False
    device_id: Optional[uuid.UUID] = None
    device_sequence: Optional[int] = None
    client_created_at: datetime
    submission_payload: dict[str, Any]
    ground_truth: dict[str, Any]

    def to_submission(self) -> ReportSubmission:
        """Convert benchmark record to a canonical domain ReportSubmission."""
        channel_ref = (
            f"batch:bench:seq:{self.device_sequence}"
            if self.device_sequence is not None
            else None
        )
        return ReportSubmission(
            disaster_id=self.disaster_id,
            source_type=self.source_type,
            source_event_id=str(self.report_id),
            source_identity=self.source_identity,
            device_id=self.device_id,
            channel_reference=channel_ref,
            raw_payload=self.submission_payload,
            client_created_at=self.client_created_at,
            language_code=self.language_code,
            idempotency_key=f"bench:{self.report_id}",
        )


class RaahatBenchDataset(BaseModel):
    """Complete frozen RaahatBench evaluation dataset containing reports and ground truths."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_id: str = "raahat-bench-v1"
    version: str = "1.0.0"
    created_at: datetime
    seed: int
    disaster_id: uuid.UUID
    num_reports: int
    num_incidents: int
    distribution_summary: dict[str, Any]
    incidents: list[GroundTruthIncident]
    reports: list[BenchmarkReportRecord]

