"""Deterministic synthetic benchmark dataset generator for RaahatBench (RAAHAT_SPEC §9.1)."""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, TypedDict

from raahat.domain.shared.enums import SourceType

from .models import (
    BenchmarkReportRecord,
    GroundTruthHousehold,
    GroundTruthIncident,
    RaahatBenchDataset,
)

# Reference Disaster Anchor: 2026 Kerala Monsoon Flash Flood
BENCHMARK_DISASTER_ID = uuid.UUID("a1b2c3d4-e5f6-47a8-b9c0-112233445566")


class RegionInfo(TypedDict):
    district: str
    area_name: str
    center_lat: float
    center_lon: float
    pincode: str
    landmarks: list[str]


REGIONS: list[RegionInfo] = [
    {
        "district": "Ernakulam",
        "area_name": "Aluva",
        "center_lat": 10.1076,
        "center_lon": 76.3516,
        "pincode": "683101",
        "landmarks": [
            "Aluva Mahadeva Temple",
            "St. Dominic Church",
            "Govt Higher Secondary School",
            "Aluva Private Bus Stand",
            "Periyar Bridge",
            "District Hospital Aluva",
            "Railway Station Road Junction",
            "Indian Oil Petrol Pump",
        ],
    },
    {
        "district": "Pathanamthitta",
        "area_name": "Chengannur",
        "center_lat": 9.3175,
        "center_lon": 76.6114,
        "pincode": "689121",
        "landmarks": [
            "Mahadeva Temple Chengannur",
            "Bethel Marthoma Church",
            "Christian College",
            "Chengannur Market Junction",
            "Pamba River Causeway",
            "Govt Taluk Hospital",
            "Kallissery Bridge",
            "HP Petrol Pump Kallissery",
        ],
    },
    {
        "district": "Alappuzha",
        "area_name": "Kuttanad",
        "center_lat": 9.3900,
        "center_lon": 76.4680,
        "pincode": "688502",
        "landmarks": [
            "Edathua St. Aloysius Church",
            "Champakulam River Jetty",
            "Govt Primary Health Centre",
            "Mankombu Rice Research Station",
            "Pallathuruthy Bridge",
            "St. Mary's School",
            "Boat Jetty Junction",
            "Bharat Petroleum Pump",
        ],
    },
    {
        "district": "Thrissur",
        "area_name": "Chalakudy",
        "center_lat": 10.3070,
        "center_lon": 76.3330,
        "pincode": "680307",
        "landmarks": [
            "Chalakudy North Temple",
            "St. Mary's Forane Church",
            "Carmel College",
            "Chalakudy Railway Station",
            "NH Bridge over Chalakudy River",
            "St. James Hospital",
            "South Junction",
            "Mala Road Crossing",
        ],
    },
    {
        "district": "Wayanad",
        "area_name": "Meppadi",
        "center_lat": 11.5510,
        "center_lon": 76.1280,
        "pincode": "673577",
        "landmarks": [
            "Meppadi Mariamman Kovil",
            "St. Joseph's Church",
            "Govt High School Chooralmala",
            "Mundakkai Bridge",
            "Tea Estate Dispensary",
            "Town Centre Bus Stop",
            "Wayanad Forest Checkpost",
            "River Crossing Point",
        ],
    },
]

FAMILY_NAMES = [
    "Nair", "Menon", "Kurian", "Mathew", "Pillai", "Varghese", "Thomas", "Nambiar",
    "Joseph", "Cherian", "Panicker", "Sharma", "Varma", "Kumar", "Iyer", "Chacko",
    "George", "Ali", "Hassan", "Koya", "Babu", "Paul", "Das", "Fernandez",
]

VULNERABLE_OPTIONS = [
    ["elderly"],
    ["infant"],
    ["pregnant_woman"],
    ["bedridden_patient"],
    ["elderly", "infant"],
    ["mobility_impaired"],
]


class RaahatBenchGenerator:
    """Generates the frozen 1,000 synthetic report dataset across 100 ground-truth incidents."""

    def __init__(self, seed: int = 42, disaster_id: uuid.UUID = BENCHMARK_DISASTER_ID) -> None:
        self.seed = seed
        self.disaster_id = disaster_id
        self.rng = random.Random(seed)

    def generate(self) -> RaahatBenchDataset:
        """Create 1,000 synthetic reports across 100 ground-truth incidents with specified distributions."""
        incidents = self._generate_incidents(num_incidents=100)
        reports = self._generate_reports(incidents=incidents, num_reports=1000)
        summary = self._calculate_summary(incidents=incidents, reports=reports)

        return RaahatBenchDataset(
            benchmark_id="raahat-bench-v1",
            version="1.0.0",
            created_at=datetime(2026, 11, 8, 0, 0, 0, tzinfo=timezone.utc),
            seed=self.seed,
            disaster_id=self.disaster_id,
            num_reports=len(reports),
            num_incidents=len(incidents),
            distribution_summary=summary,
            incidents=incidents,
            reports=reports,
        )

    def _generate_incidents(self, num_incidents: int = 100) -> list[GroundTruthIncident]:
        """Generate 100 realistic ground-truth incidents with households and geographic grounding."""
        incidents: list[GroundTruthIncident] = []

        severities = ["critical"] * 25 + ["urgent"] * 45 + ["standard"] * 20 + ["low"] * 10
        self.rng.shuffle(severities)

        for i in range(num_incidents):
            region = REGIONS[i % len(REGIONS)]
            incident_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"incident-{self.seed}-{i}")
            code = f"INC-{i+1:03d}"

            # Spatial jitter around region center (up to ~3 km radius)
            lat_jitter = self.rng.uniform(-0.025, 0.025)
            lon_jitter = self.rng.uniform(-0.025, 0.025)
            lat = round(region["center_lat"] + lat_jitter, 6)
            lon = round(region["center_lon"] + lon_jitter, 6)

            landmark = self.rng.choice(region["landmarks"])
            severity = severities[i]

            if severity == "critical":
                water_depth = self.rng.uniform(180.0, 320.0)
                water_trend = "rising"
                trapped = self.rng.choice(["trapped_roof", "trapped_upper_floor"])
                has_medical = self.rng.choice([True, False])
                has_vulnerable = True
            elif severity == "urgent":
                water_depth = self.rng.uniform(110.0, 180.0)
                water_trend = self.rng.choice(["rising", "stable"])
                trapped = self.rng.choice(["trapped_upper_floor", "ground_submerged"])
                has_medical = self.rng.choice([True, False])
                has_vulnerable = self.rng.choice([True, False])
            elif severity == "standard":
                water_depth = self.rng.uniform(50.0, 110.0)
                water_trend = self.rng.choice(["stable", "receding"])
                trapped = "ground_submerged"
                has_medical = False
                has_vulnerable = self.rng.choice([True, False])
            else:  # low
                water_depth = self.rng.uniform(15.0, 50.0)
                water_trend = "receding"
                trapped = "none"
                has_medical = False
                has_vulnerable = False

            # Generate 1 to 3 households per incident cluster
            num_hh = self.rng.choices([1, 2, 3], weights=[0.65, 0.25, 0.10])[0]
            households: list[GroundTruthHousehold] = []
            incident_people_count = 0

            for h_idx in range(num_hh):
                hh_id = f"{code}-HH{h_idx+1}"
                family = self.rng.choice(FAMILY_NAMES)
                hh_people = self.rng.randint(2, 7)
                incident_people_count += hh_people

                vulnerable = (
                    self.rng.choice(VULNERABLE_OPTIONS)
                    if (has_vulnerable and h_idx == 0) or self.rng.random() < 0.25
                    else []
                )
                hh_medical = (has_medical and h_idx == 0) or (self.rng.random() < 0.15)
                med_desc = (
                    self.rng.choice([
                        "Diabetic elderly requiring daily insulin",
                        "High fever and chest pain",
                        "Dialysis patient stranded",
                        "Severe hypothermia and dehydration",
                    ])
                    if hh_medical
                    else None
                )

                households.append(
                    GroundTruthHousehold(
                        household_id=hh_id,
                        family_name=family,
                        people_count=hh_people,
                        vulnerable_members=vulnerable,
                        has_medical_emergency=hh_medical,
                        medical_emergency_details=med_desc,
                        floor=self.rng.choice([1, 2, 3]) if trapped != "none" else 1,
                        location_name=f"{family} Residence, near {landmark}",
                        latitude=round(lat + self.rng.uniform(-0.0008, 0.0008), 6),
                        longitude=round(lon + self.rng.uniform(-0.0008, 0.0008), 6),
                    )
                )

            incidents.append(
                GroundTruthIncident(
                    incident_id=incident_id,
                    incident_code=code,
                    title=f"Flood distress at {region['area_name']} near {landmark}",
                    disaster_id=self.disaster_id,
                    landmark_name=landmark,
                    area_name=region["area_name"],
                    district=region["district"],
                    pincode=region["pincode"],
                    latitude=lat,
                    longitude=lon,
                    true_severity=severity,
                    water_depth_cm=round(water_depth, 1),
                    water_trend=water_trend,
                    trapped_status=trapped,
                    total_people=incident_people_count,
                    has_medical_emergency=has_medical,
                    has_vulnerable_people=has_vulnerable,
                    households=households,
                )
            )

        return incidents

    def _generate_reports(
        self,
        incidents: list[GroundTruthIncident],
        num_reports: int = 1000,
    ) -> list[BenchmarkReportRecord]:
        """Generate 1,000 reports across ground-truth incidents with specified distribution targets."""
        # 1. Target counts from RAAHAT_SPEC §9.1:
        # Direct victim: 35% -> 350
        # Relative / third-party: 25% -> 250
        # Volunteer reports: 20% -> 200
        # Shelter/responder: 20% -> 200
        relationships = (
            ["direct"] * 350
            + ["relative"] * 250
            + ["volunteer"] * 200
            + ["responder"] * 200
        )
        self.rng.shuffle(relationships)

        # 2. Target anomalies:
        # Duplicate/overlapping: ~30% (300)
        # Contradictions: ~12% (120)
        # Ambiguous locations: ~25% (250)
        # Missing critical fields: ~25% (250)
        duplicate_flags = [True] * 300 + [False] * 700
        contradiction_flags = [True] * 120 + [False] * 880
        ambiguous_flags = [True] * 250 + [False] * 750
        missing_flags = [True] * 250 + [False] * 750

        self.rng.shuffle(duplicate_flags)
        self.rng.shuffle(contradiction_flags)
        self.rng.shuffle(ambiguous_flags)
        self.rng.shuffle(missing_flags)

        # Allocate base incident index for each report
        # High-severity incidents get more reports (hotspot concentration)
        incident_weights = [
            4.0 if inc.true_severity == "critical"
            else 2.5 if inc.true_severity == "urgent"
            else 1.5 if inc.true_severity == "standard"
            else 1.0
            for inc in incidents
        ]
        assigned_incidents = self.rng.choices(incidents, weights=incident_weights, k=num_reports)

        reports: list[BenchmarkReportRecord] = []
        base_time = datetime(2026, 11, 7, 6, 0, 0, tzinfo=timezone.utc)

        # Volunteer device sequence tracking for offline sync simulation
        device_pool = [
            uuid.uuid5(uuid.NAMESPACE_DNS, f"volunteer-device-{self.seed}-{d}")
            for d in range(1, 6)
        ]
        device_sequences: dict[uuid.UUID, int] = {d: 0 for d in device_pool}

        for idx in range(num_reports):
            report_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"report-{self.seed}-{idx}")
            incident = assigned_incidents[idx]
            rel = relationships[idx]

            # Choose source type matching relationship
            if rel == "direct":
                source_type = self.rng.choice([SourceType.IVR, SourceType.SMS, SourceType.WEB])
            elif rel == "relative":
                source_type = self.rng.choice([SourceType.WEB, SourceType.IVR, SourceType.SMS])
            elif rel == "volunteer":
                source_type = SourceType.VOLUNTEER
            else:  # responder
                source_type = self.rng.choice([SourceType.RADIO, SourceType.WEB])

            is_duplicate = duplicate_flags[idx]
            has_contradiction = contradiction_flags[idx]
            is_ambiguous = ambiguous_flags[idx]
            has_missing = missing_flags[idx]

            # Pick target household
            household: Optional[GroundTruthHousehold] = None
            if incident.households:
                household = self.rng.choice(incident.households)

            # Language modes
            lang_mode = self.rng.choices(
                ["code_switched", "english", "hindi", "malayalam"],
                weights=[0.45, 0.25, 0.15, 0.15],
            )[0]
            lang_code = "en" if lang_mode == "english" else ("hi" if lang_mode == "hindi" else "ml")

            # Missing fields
            missing_fields: list[str] = []
            if has_missing:
                missing_candidates = ["people_count", "trapped_status", "medical_need", "water_depth"]
                missing_fields = self.rng.sample(
                    missing_candidates, k=self.rng.randint(1, 2)
                )

            # Contradiction type
            contradiction_type: Optional[str] = None
            if has_contradiction:
                contradiction_type = self.rng.choice([
                    "water_level_inverted",
                    "exaggerated_headcount",
                    "premature_evacuation",
                ])

            # Generate synthetic text, landmarks, and raw payload
            raw_text, landmarks = self._compose_report_text(
                incident=incident,
                household=household,
                relationship=rel,
                language_mode=lang_mode,
                is_ambiguous=is_ambiguous,
                has_contradiction=has_contradiction,
                contradiction_type=contradiction_type,
                missing_fields=missing_fields,
            )

            # Audio metadata for IVR / radio channels
            audio_meta: Optional[dict[str, Any]] = None
            if source_type in (SourceType.IVR, SourceType.RADIO):
                audio_meta = {
                    "sample_rate": 16000,
                    "duration_seconds": round(self.rng.uniform(6.0, 35.0), 1),
                    "snr_db": round(self.rng.uniform(4.0, 22.0), 1),
                    "is_clipped": self.rng.random() < 0.20,
                    "background_noise": self.rng.choice(["rain_roaring", "motor_boat", "wind", "chatter"]),
                }

            # Offline sync metadata for volunteer field app
            dev_id: Optional[uuid.UUID] = None
            dev_seq: Optional[int] = None
            is_offline = source_type == SourceType.VOLUNTEER
            if is_offline:
                dev_id = self.rng.choice(device_pool)
                device_sequences[dev_id] += 1
                dev_seq = device_sequences[dev_id]

            created_at = base_time + timedelta(
                minutes=self.rng.randint(0, 720) + (idx // 2)
            )

            submission_payload: dict[str, Any] = {
                "text": raw_text,
                "relationship": rel,
                "landmarks": landmarks,
                "caller_phone": f"+9198{self.rng.randint(10000000, 99999999)}",
            }
            if audio_meta:
                submission_payload["audio"] = audio_meta

            ground_truth_dict = {
                "incident_id": str(incident.incident_id),
                "incident_code": incident.incident_code,
                "true_severity": incident.true_severity,
                "true_latitude": incident.latitude,
                "true_longitude": incident.longitude,
                "true_area": incident.area_name,
                "true_landmark": incident.landmark_name,
                "true_people": incident.total_people,
                "true_trapped": incident.trapped_status,
                "has_medical": incident.has_medical_emergency,
                "household_id": household.household_id if household else None,
            }

            reports.append(
                BenchmarkReportRecord(
                    report_id=report_id,
                    disaster_id=self.disaster_id,
                    ground_truth_incident_id=incident.incident_id,
                    ground_truth_household_id=household.household_id if household else None,
                    source_type=source_type,
                    source_identity=f"phone:+9198{self.rng.randint(10000000, 99999999)}" if source_type != SourceType.RADIO else f"radio:ch-{self.rng.randint(1, 16)}",
                    relationship=rel,
                    language_code=lang_code,
                    language_mode=lang_mode,
                    raw_text=raw_text,
                    audio_metadata=audio_meta,
                    mentioned_landmarks=landmarks,
                    is_location_ambiguous=is_ambiguous,
                    has_contradiction=has_contradiction,
                    contradiction_type=contradiction_type,
                    has_missing_fields=has_missing,
                    missing_fields=missing_fields,
                    is_duplicate=is_duplicate,
                    is_offline_sync=is_offline,
                    device_id=dev_id,
                    device_sequence=dev_seq,
                    client_created_at=created_at,
                    submission_payload=submission_payload,
                    ground_truth=ground_truth_dict,
                )
            )

        return reports

    def _compose_report_text(
        self,
        incident: GroundTruthIncident,
        household: Optional[GroundTruthHousehold],
        relationship: str,
        language_mode: str,
        is_ambiguous: bool,
        has_contradiction: bool,
        contradiction_type: Optional[str],
        missing_fields: list[str],
    ) -> tuple[str, list[str]]:
        """Compose realistic distress report text reflecting linguistics, ambiguities, and contradictions."""
        landmarks: list[str] = []

        if is_ambiguous:
            # Ambiguous location: generic description or just "near temple" / "market area"
            loc_desc = self.rng.choice([
                f"near temple in {incident.area_name}",
                f"{incident.area_name} bypass road",
                "near old school building",
                "beside the big bridge, water everywhere",
                "somewhere near market side",
            ])
            landmarks = ["temple" if "temple" in loc_desc else "school"]
        else:
            loc_desc = f"{household.family_name if household else 'house'} near {incident.landmark_name}, {incident.area_name}"
            landmarks = [incident.landmark_name]

        # People count
        if "people_count" in missing_fields:
            people_desc = "some people"
        elif has_contradiction and contradiction_type == "exaggerated_headcount":
            people_desc = f"{incident.total_people + self.rng.randint(15, 30)} people"
        else:
            people_desc = f"{household.people_count if household else incident.total_people} people"

        # Water level
        if "water_depth" in missing_fields:
            water_desc = "water entering"
        elif has_contradiction and contradiction_type == "water_level_inverted":
            water_desc = "water is slowly draining away, seems okay now"
        else:
            water_desc = f"water is rising rapidly, above {int(incident.water_depth_cm)} cm"

        # Trapped status
        if "trapped_status" in missing_fields:
            trapped_desc = "stranded"
        elif has_contradiction and contradiction_type == "premature_evacuation":
            trapped_desc = "everyone was already rescued by neighbors"
        else:
            trapped_desc = "trapped on the upper floor / terrace" if incident.trapped_status != "none" else "safe on high ground"

        # Medical note
        medical_desc = ""
        if "medical_need" not in missing_fields and incident.has_medical_emergency:
            medical_desc = "Urgent: elderly diabetic patient needs medicine and oxygen."

        # Template by relationship and language
        if language_mode == "code_switched":
            if relationship == "direct":
                text = (
                    f"Help needed immediately! Hum log {loc_desc} par phanse hain. {water_desc}. "
                    f"There are {people_desc} {trapped_desc}. {medical_desc} Please send rescue boat urgently!"
                )
            elif relationship == "relative":
                text = (
                    f"Reporting for my parents and family at {loc_desc}. Phone battery dying. "
                    f"{people_desc} trapped there. {water_desc}. {medical_desc} Please rescue them!"
                )
            elif relationship == "volunteer":
                text = (
                    f"Field volunteer report: Landmark {loc_desc}. Observed {people_desc}, {trapped_desc}. "
                    f"{water_desc}. Access only possible via inflatable dinghy."
                )
            else:  # responder
                text = (
                    f"Radio dispatch relay: Spot rep from {loc_desc}. Headcount approximately {people_desc}. "
                    f"Status: {trapped_desc}. {water_desc}. Operational priority high."
                )
        elif language_mode == "hindi":
            text = (
                f"Kripya madad karein! Hum {loc_desc} ke paas phanse hue hain. {water_desc}. "
                f"Yahan {people_desc} {trapped_desc} hain. {medical_desc} Jaldi naav bhejiye!"
            )
        elif language_mode == "malayalam":
            text = (
                f"Rakshikkanam! {loc_desc} il vellam keri aalkkar pettupoyi. {water_desc}. "
                f"{people_desc} {trapped_desc}. {medical_desc} Rescue boat udan ayakkuka!"
            )
        else:  # english
            text = (
                f"Emergency SOS distress call: Location {loc_desc}. {water_desc}. "
                f"Current situation: {people_desc} are {trapped_desc}. {medical_desc} Immediate evacuation required."
            )

        return text.strip(), landmarks

    def _calculate_summary(
        self,
        incidents: list[GroundTruthIncident],
        reports: list[BenchmarkReportRecord],
    ) -> dict[str, Any]:
        """Compute statistical breakdown verifying alignment with RAAHAT_SPEC §9.1 coverage targets."""
        total_reports = len(reports)
        rel_counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        lang_counts: dict[str, int] = {}

        for r in reports:
            rel_counts[r.relationship] = rel_counts.get(r.relationship, 0) + 1
            source_counts[r.source_type.value] = source_counts.get(r.source_type.value, 0) + 1
            lang_counts[r.language_mode] = lang_counts.get(r.language_mode, 0) + 1

        duplicates = sum(1 for r in reports if r.is_duplicate)
        contradictions = sum(1 for r in reports if r.has_contradiction)
        ambiguous = sum(1 for r in reports if r.is_location_ambiguous)
        missing = sum(1 for r in reports if r.has_missing_fields)
        offline = sum(1 for r in reports if r.is_offline_sync)

        severity_counts: dict[str, int] = {}
        for inc in incidents:
            severity_counts[inc.true_severity] = severity_counts.get(inc.true_severity, 0) + 1

        return {
            "total_reports": total_reports,
            "total_ground_truth_incidents": len(incidents),
            "severity_distribution": severity_counts,
            "relationship_distribution": {
                k: {"count": v, "percentage": round((v / total_reports) * 100, 1)}
                for k, v in rel_counts.items()
            },
            "source_type_distribution": {
                k: {"count": v, "percentage": round((v / total_reports) * 100, 1)}
                for k, v in source_counts.items()
            },
            "language_mode_distribution": {
                k: {"count": v, "percentage": round((v / total_reports) * 100, 1)}
                for k, v in lang_counts.items()
            },
            "anomalies": {
                "duplicate_reports": {"count": duplicates, "percentage": round((duplicates / total_reports) * 100, 1)},
                "contradictory_reports": {"count": contradictions, "percentage": round((contradictions / total_reports) * 100, 1)},
                "ambiguous_locations": {"count": ambiguous, "percentage": round((ambiguous / total_reports) * 100, 1)},
                "missing_critical_fields": {"count": missing, "percentage": round((missing / total_reports) * 100, 1)},
                "offline_synced_reports": {"count": offline, "percentage": round((offline / total_reports) * 100, 1)},
            },
        }

    @staticmethod
    def save_dataset(dataset: RaahatBenchDataset, output_dir: Path | str) -> dict[str, Path]:
        """Save complete frozen dataset files to disk."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        full_dataset_file = out_path / "raahat_bench_1000.json"
        incidents_file = out_path / "ground_truth_incidents.json"
        metadata_file = out_path / "metadata.json"

        # 1. Full benchmark JSON
        full_dataset_file.write_text(dataset.model_dump_json(indent=2), encoding="utf-8")

        # 2. Ground truth incidents JSON (for fast reference during evaluation)
        incidents_data = [inc.model_dump(mode="json") for inc in dataset.incidents]
        incidents_file.write_text(json.dumps(incidents_data, indent=2), encoding="utf-8")

        # 3. Metadata summary JSON
        metadata = {
            "benchmark_id": dataset.benchmark_id,
            "version": dataset.version,
            "created_at": dataset.created_at.isoformat(),
            "seed": dataset.seed,
            "disaster_id": str(dataset.disaster_id),
            "num_reports": dataset.num_reports,
            "num_incidents": dataset.num_incidents,
            "summary": dataset.distribution_summary,
        }
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return {
            "dataset": full_dataset_file,
            "incidents": incidents_file,
            "metadata": metadata_file,
        }

    @staticmethod
    def load_dataset(input_path: Path | str) -> RaahatBenchDataset:
        """Load frozen benchmark dataset from disk."""
        path = Path(input_path)
        content = path.read_text(encoding="utf-8")
        return RaahatBenchDataset.model_validate_json(content)
