"""Unit tests for ConservativeIncidentMatcher, scoring signals, and feature extraction."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.application.incident_resolution.matcher import (
    ConservativeIncidentMatcher,
    extract_coordinates,
    extract_name,
    extract_phone,
    normalize_phone,
)
from raahat.application.incident_resolution.models import IncidentSnapshot
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.incidents.incident import Incident
from raahat.domain.reports.report import Report
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import (
    IncidentLinkType,
    IncidentStatus,
    ProcessingStatus,
    SourceType,
    VerificationStatus,
)


def _make_report(
    payload: dict,
    disaster_id: uuid.UUID | None = None,
    source_identity: str | None = None,
    channel_reference: str | None = None,
    report_id: uuid.UUID | None = None,
) -> Report:
    return Report(
        id=report_id or uuid.uuid4(),
        disaster_id=disaster_id or uuid.uuid4(),
        source_type=SourceType.WEB,
        source_identity=source_identity,
        channel_reference=channel_reference,
        raw_payload=payload,
        received_at=datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc),
        client_created_at=datetime(2026, 8, 15, 11, 55, 0, tzinfo=timezone.utc),
        idempotency_key=f"rep-{uuid.uuid4().hex}",
        processing_status=ProcessingStatus.PENDING,
    )


class TestFeatureExtraction:
    def test_normalize_phone_formats(self) -> None:
        assert normalize_phone("+91 98765 43210") == "9876543210"
        assert normalize_phone("919876543210") == "9876543210"
        assert normalize_phone("09876543210") == "9876543210"
        assert normalize_phone("9876543210") == "9876543210"
        assert normalize_phone("1234567") == "1234567"
        assert normalize_phone("1234") is None
        assert normalize_phone(None) is None
        assert normalize_phone("") is None

    def test_extract_phone_from_various_sources(self) -> None:
        # 1. source_identity
        r1 = _make_report({}, source_identity="+91 98765 43210")
        assert extract_phone(r1) == "9876543210"

        # 2. channel_reference
        r2 = _make_report({}, channel_reference="+918888877777")
        assert extract_phone(r2) == "8888877777"

        # 3. raw_payload direct
        r3 = _make_report({"phone": "9999911111"})
        assert extract_phone(r3) == "9999911111"

        # 4. raw_payload nested in parsed
        r4 = _make_report({"parsed": {"caller_number": "9123456789"}})
        assert extract_phone(r4) == "9123456789"

    def test_extract_coordinates_from_various_formats(self) -> None:
        # lat/lon direct
        r1 = _make_report({"latitude": 19.0760, "longitude": 72.8777})
        c1 = extract_coordinates(r1)
        assert c1 is not None
        assert abs(c1.latitude - 19.0760) < 1e-4
        assert abs(c1.longitude - 72.8777) < 1e-4

        # nested location dict
        r2 = _make_report({"location": {"lat": 18.5204, "lon": 73.8567}})
        c2 = extract_coordinates(r2)
        assert c2 is not None
        assert abs(c2.latitude - 18.5204) < 1e-4

        # GeoJSON [lon, lat] list
        r3 = _make_report({"coordinates": [73.8567, 18.5204]})
        c3 = extract_coordinates(r3)
        assert c3 is not None
        assert abs(c3.latitude - 18.5204) < 1e-4
        assert abs(c3.longitude - 73.8567) < 1e-4

        # invalid coords return None
        r4 = _make_report({"latitude": 150.0, "longitude": 200.0})
        assert extract_coordinates(r4) is None

        # missing coords
        r5 = _make_report({"text": "no location"})
        assert extract_coordinates(r5) is None

    def test_extract_name(self) -> None:
        r1 = _make_report({"name": "Ramesh Kumar"})
        assert extract_name(r1) == "Ramesh Kumar"

        r2 = _make_report({"parsed": {"caller_name": "Sunita Patil"}})
        assert extract_name(r2) == "Sunita Patil"


class TestConservativeIncidentMatcher:
    def test_match_exact_phone_and_close_distance_gives_high_score(self) -> None:
        disaster_id = uuid.uuid4()
        r_coords = PointCoordinates(latitude=18.5200, longitude=73.8500)
        report = _make_report(
            payload={"latitude": r_coords.latitude, "longitude": r_coords.longitude, "people_count": 4},
            disaster_id=disaster_id,
            source_identity="+919876543210",
        )

        inc_id = uuid.uuid4()
        incident = Incident(id=inc_id, disaster_id=disaster_id)
        # 25 meters away
        hyp_coords = PointCoordinates(latitude=18.5202, longitude=73.8501)
        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=inc_id,
            coordinates=hyp_coords,
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )
        linked_report = _make_report(
            payload={"people_count": 4},
            disaster_id=disaster_id,
            source_identity="+919876543210",
        )

        snapshot = IncidentSnapshot(
            incident=incident,
            hypotheses=[hyp],
            reports=[linked_report],
            evidence_items=[],
        )

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        candidates = matcher.find_candidates(report)

        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.incident_id == inc_id
        assert cand.score >= 0.85
        assert cand.spatial_distance_m is not None
        assert cand.spatial_distance_m <= 35.0
        assert not cand.conflicts
        assert cand.suggested_link_type == IncidentLinkType.POSSIBLE_DUPLICATE

    def test_match_differing_phone_penalizes_score(self) -> None:
        disaster_id = uuid.uuid4()
        report = _make_report(
            payload={"latitude": 18.5200, "longitude": 73.8500},
            disaster_id=disaster_id,
            source_identity="+919876543210",
        )

        inc_id = uuid.uuid4()
        incident = Incident(id=inc_id, disaster_id=disaster_id)
        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=inc_id,
            coordinates=PointCoordinates(latitude=18.5200, longitude=73.8500),
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )
        # Different phone
        linked_report = _make_report({}, disaster_id=disaster_id, source_identity="+911111122222")

        snapshot = IncidentSnapshot(
            incident=incident,
            hypotheses=[hyp],
            reports=[linked_report],
        )

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        candidates = matcher.find_candidates(report)

        assert len(candidates) == 1
        cand = candidates[0]
        # Diff phone penalty drops composite score significantly
        assert cand.score < 0.80

    def test_distance_falloff_scoring(self) -> None:
        disaster_id = uuid.uuid4()
        origin = PointCoordinates(latitude=18.5200, longitude=73.8500)
        report = _make_report(
            payload={"latitude": origin.latitude, "longitude": origin.longitude},
            disaster_id=disaster_id,
        )

        # Distant incident: ~2 km away (latitude +0.02 is ~2.2km)
        distant_coords = PointCoordinates(latitude=18.5400, longitude=73.8500)
        inc_id = uuid.uuid4()
        incident = Incident(id=inc_id, disaster_id=disaster_id)
        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=inc_id,
            coordinates=distant_coords,
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )

        snapshot = IncidentSnapshot(incident=incident, hypotheses=[hyp])
        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        candidates = matcher.find_candidates(report)

        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.spatial_distance_m is not None
        assert cand.spatial_distance_m > 1000.0
        assert cand.score < 0.40

    def test_severe_contradiction_is_flagged_and_capped(self) -> None:
        disaster_id = uuid.uuid4()
        rep_a_id = uuid.uuid4()
        rep_b_id = uuid.uuid4()

        # Incoming report claims water rising
        report = _make_report(
            payload={
                "latitude": 18.5200,
                "longitude": 73.8500,
                "water_level_trend": "rising",
                "phone": "+919876543210",
            },
            disaster_id=disaster_id,
            report_id=rep_a_id,
            source_identity="+919876543210",
        )

        # Candidate incident report claims water receded
        inc_id = uuid.uuid4()
        incident = Incident(id=inc_id, disaster_id=disaster_id)
        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=inc_id,
            coordinates=PointCoordinates(latitude=18.5200, longitude=73.8500),
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )
        linked_report = _make_report(
            payload={
                "latitude": 18.5200,
                "longitude": 73.8500,
                "water_level_trend": "receded",
                "phone": "+919876543210",
            },
            disaster_id=disaster_id,
            report_id=rep_b_id,
            source_identity="+919876543210",
        )

        # Build evidence items
        ev_a = EvidenceItem(
            id=uuid.uuid4(),
            report_id=rep_a_id,
            subject_type="incident",
            attribute="water_level_trend",
            value="rising",
            spans=(),
        )
        ev_b = EvidenceItem(
            id=uuid.uuid4(),
            report_id=rep_b_id,
            subject_type="incident",
            attribute="water_level_trend",
            value="receded",
            spans=(),
        )

        snapshot = IncidentSnapshot(
            incident=incident,
            hypotheses=[hyp],
            reports=[linked_report],
            evidence_items=[ev_b],
        )

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        candidates = matcher.find_candidates(report, evidence_items=[ev_a])

        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.suggested_link_type == IncidentLinkType.CONFLICTING
        assert len(cand.conflicts) > 0
        assert any("water_level_trend" in c for c in cand.conflicts)
        # Score must be strictly capped <= 0.50 due to severe contradiction
        assert cand.score <= 0.50

    def test_resolved_and_closed_incidents_are_ignored(self) -> None:
        disaster_id = uuid.uuid4()
        report = _make_report({"latitude": 18.5200, "longitude": 73.8500}, disaster_id=disaster_id)

        inc_resolved = Incident(id=uuid.uuid4(), disaster_id=disaster_id, status=IncidentStatus.RESOLVED)
        inc_closed = Incident(id=uuid.uuid4(), disaster_id=disaster_id, status=IncidentStatus.CLOSED)

        matcher = ConservativeIncidentMatcher(
            snapshot_provider=lambda d_id: [
                IncidentSnapshot(incident=inc_resolved),
                IncidentSnapshot(incident=inc_closed),
            ]
        )
        candidates = matcher.find_candidates(report)
        assert len(candidates) == 0
