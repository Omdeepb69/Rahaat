"""Unit tests for Task 1.3 — Core Domain Entities & Value Objects.

Each test verifies the public contract (construction, validation, immutability,
defaults) without touching any database, framework, or vendor library.
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from raahat.domain.evidence.evidence import EvidenceItem, EvidenceSpan
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.households.household import Household, Person
from raahat.domain.incidents.incident import Incident, IncidentLink, IncidentReportLink
from raahat.domain.operations.operation import Assignment, OperationEvent, Resource
from raahat.domain.reports.report import Report, ReportSubmission
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import (
    AssignmentStatus,
    IdentityStatus,
    IncidentLinkType,
    IncidentStatus,
    OperationEventType,
    PriorityLevel,
    ProcessingStatus,
    RelationshipType,
    ResourceStatus,
    ResourceType,
    SourceType,
    VerificationStatus,
)
from raahat.domain.triage.assessment import PriorityAssessment

# ---------------------------------------------------------------------------
# PointCoordinates
# ---------------------------------------------------------------------------


class TestPointCoordinates:
    def test_valid_construction(self) -> None:
        pt = PointCoordinates(latitude=12.9716, longitude=77.5946)
        assert pt.latitude == 12.9716
        assert pt.longitude == 77.5946

    def test_boundary_values(self) -> None:
        PointCoordinates(latitude=-90.0, longitude=-180.0)
        PointCoordinates(latitude=90.0, longitude=180.0)

    def test_invalid_latitude_raises(self) -> None:
        with pytest.raises(ValidationError):
            PointCoordinates(latitude=91.0, longitude=0.0)

    def test_invalid_longitude_raises(self) -> None:
        with pytest.raises(ValidationError):
            PointCoordinates(latitude=0.0, longitude=181.0)

    def test_negative_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            PointCoordinates(latitude=-91.0, longitude=0.0)

    def test_to_wkt(self) -> None:
        pt = PointCoordinates(latitude=12.9716, longitude=77.5946)
        wkt = pt.to_wkt()
        assert wkt.startswith("POINT(")
        # WKT order: longitude latitude
        assert "77.5946000" in wkt
        assert "12.9716000" in wkt

    def test_from_wkt_roundtrip(self) -> None:
        original = PointCoordinates(latitude=28.6139, longitude=77.2090)
        recovered = PointCoordinates.from_wkt(original.to_wkt())
        assert abs(recovered.latitude - original.latitude) < 1e-6
        assert abs(recovered.longitude - original.longitude) < 1e-6

    def test_from_wkt_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid WKT"):
            PointCoordinates.from_wkt("LINESTRING(0 0, 1 1)")

    def test_distance_to_same_point_is_zero(self) -> None:
        pt = PointCoordinates(latitude=0.0, longitude=0.0)
        assert pt.distance_to(pt) == pytest.approx(0.0)

    def test_distance_to_known_value(self) -> None:
        # Equator: 1 degree longitude ≈ 111 320 m
        a = PointCoordinates(latitude=0.0, longitude=0.0)
        b = PointCoordinates(latitude=0.0, longitude=1.0)
        dist = a.distance_to(b)
        assert 111_000 < dist < 112_000

    def test_frozen(self) -> None:
        pt = PointCoordinates(latitude=0.0, longitude=0.0)
        with pytest.raises((TypeError, ValidationError)):
            pt.latitude = 10.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Report / ReportSubmission
# ---------------------------------------------------------------------------


class TestReport:
    def _make_disaster_id(self) -> uuid.UUID:
        return uuid.uuid4()

    def test_default_processing_status_is_pending(self) -> None:
        did = self._make_disaster_id()
        r = Report(
            disaster_id=did,
            source_type=SourceType.IVR,
            raw_payload={"raw": "data"},
            idempotency_key="k-1",
        )
        assert r.processing_status is ProcessingStatus.PENDING

    def test_id_auto_generated(self) -> None:
        did = self._make_disaster_id()
        r1 = Report(disaster_id=did, source_type=SourceType.SMS, raw_payload={}, idempotency_key="k")
        r2 = Report(disaster_id=did, source_type=SourceType.SMS, raw_payload={}, idempotency_key="k")
        assert r1.id != r2.id

    def test_frozen(self) -> None:
        did = self._make_disaster_id()
        r = Report(disaster_id=did, source_type=SourceType.WEB, raw_payload={}, idempotency_key="k")
        with pytest.raises((TypeError, ValidationError)):
            r.processing_status = ProcessingStatus.PROCESSED  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Report(  # type: ignore[call-arg]
                disaster_id=uuid.uuid4(),
                source_type=SourceType.WEB,
                raw_payload={},
                idempotency_key="k",
                unknown_field="x",
            )


class TestReportSubmission:
    def _base_submission(self, **kwargs: object) -> ReportSubmission:
        return ReportSubmission(
            disaster_id=uuid.uuid4(),
            source_type=SourceType.IVR,
            raw_payload={"key": "value"},
            **kwargs,  # type: ignore[arg-type]
        )

    def test_to_report_produces_pending_report(self) -> None:
        sub = self._base_submission(source_event_id="evt-001")
        report = sub.to_report()
        assert isinstance(report, Report)
        assert report.processing_status is ProcessingStatus.PENDING

    def test_to_report_idempotency_key_uses_provided_value(self) -> None:
        sub = self._base_submission(idempotency_key="my-key")
        report = sub.to_report()
        assert report.idempotency_key == "my-key"

    def test_to_report_idempotency_key_derived_from_source_when_absent(self) -> None:
        sub = self._base_submission(source_event_id="evt-002")
        report = sub.to_report()
        assert report.idempotency_key.startswith("ivr-evt-002")

    def test_to_report_idempotency_key_uses_uuid_when_no_source_event(self) -> None:
        sub = self._base_submission()
        report = sub.to_report()
        # Derived key starts with source_type prefix
        assert report.idempotency_key.startswith("ivr-")

    def test_to_report_respects_explicit_report_id(self) -> None:
        fixed_id = uuid.uuid4()
        sub = self._base_submission()
        report = sub.to_report(report_id=fixed_id)
        assert report.id == fixed_id


# ---------------------------------------------------------------------------
# EvidenceItem / EvidenceSpan
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def _make(self, **kwargs: object) -> EvidenceItem:
        return EvidenceItem(
            report_id=uuid.uuid4(),
            subject_type="person",
            attribute="location",
            value="somewhere",
            **kwargs,  # type: ignore[arg-type]
        )

    def test_confidence_zero_ok(self) -> None:
        item = self._make(confidence=0.0)
        assert item.confidence == 0.0

    def test_confidence_one_ok(self) -> None:
        item = self._make(confidence=1.0)
        assert item.confidence == 1.0

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make(confidence=1.5)

    def test_confidence_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make(confidence=-0.1)

    def test_confidence_none_by_default(self) -> None:
        item = self._make()
        assert item.confidence is None

    def test_default_verification_status(self) -> None:
        item = self._make()
        assert item.verification_status is VerificationStatus.UNVERIFIED

    def test_spans_are_tuple(self) -> None:
        span = EvidenceSpan(text="in the flood area")
        item = self._make(spans=(span,))
        assert isinstance(item.spans, tuple)
        assert item.spans[0].text == "in the flood area"

    def test_spans_immutable(self) -> None:
        item = self._make()
        with pytest.raises((TypeError, AttributeError, ValidationError)):
            item.spans = ()  # type: ignore[misc]

    def test_frozen(self) -> None:
        item = self._make()
        with pytest.raises((TypeError, ValidationError)):
            item.attribute = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Household / Person
# ---------------------------------------------------------------------------


class TestPerson:
    def test_default_identity_status_unverified(self) -> None:
        p = Person()
        assert p.identity_status is IdentityStatus.UNVERIFIED

    def test_id_auto_generated(self) -> None:
        assert Person().id != Person().id

    def test_frozen(self) -> None:
        p = Person()
        with pytest.raises((TypeError, ValidationError)):
            p.display_label = "changed"  # type: ignore[misc]


class TestHousehold:
    def test_default_identity_status_unverified(self) -> None:
        hh = Household(disaster_id=uuid.uuid4())
        assert hh.identity_status is IdentityStatus.UNVERIFIED

    def test_members_are_tuple(self) -> None:
        p = Person()
        hh = Household(disaster_id=uuid.uuid4(), members=(p,))
        assert isinstance(hh.members, tuple)
        assert hh.members[0] is p

    def test_members_empty_by_default(self) -> None:
        hh = Household(disaster_id=uuid.uuid4())
        assert hh.members == ()

    def test_frozen(self) -> None:
        hh = Household(disaster_id=uuid.uuid4())
        with pytest.raises((TypeError, ValidationError)):
            hh.display_label = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Incident / IncidentLink / IncidentReportLink
# ---------------------------------------------------------------------------


class TestIncident:
    def test_defaults(self) -> None:
        inc = Incident(disaster_id=uuid.uuid4())
        assert inc.status is IncidentStatus.UNVERIFIED
        assert inc.operational_priority is PriorityLevel.UNASSESSED
        assert inc.last_confirmed_at is None
        assert inc.severity_facts == {}

    def test_id_auto_generated(self) -> None:
        did = uuid.uuid4()
        assert Incident(disaster_id=did).id != Incident(disaster_id=did).id

    def test_frozen(self) -> None:
        inc = Incident(disaster_id=uuid.uuid4())
        with pytest.raises((TypeError, ValidationError)):
            inc.status = IncidentStatus.RESOLVED  # type: ignore[misc]


class TestIncidentLink:
    def test_confidence_boundaries(self) -> None:
        a, b = uuid.uuid4(), uuid.uuid4()
        IncidentLink(incident_a_id=a, incident_b_id=b, link_type=IncidentLinkType.RELATED_CLUSTER, confidence=0.0)
        IncidentLink(incident_a_id=a, incident_b_id=b, link_type=IncidentLinkType.RELATED_CLUSTER, confidence=1.0)

    def test_confidence_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            IncidentLink(
                incident_a_id=uuid.uuid4(),
                incident_b_id=uuid.uuid4(),
                link_type=IncidentLinkType.CONFLICTING,
                confidence=1.1,
            )

    def test_confidence_none_by_default(self) -> None:
        link = IncidentLink(
            incident_a_id=uuid.uuid4(),
            incident_b_id=uuid.uuid4(),
            link_type=IncidentLinkType.POSSIBLE_DUPLICATE,
        )
        assert link.confidence is None


class TestIncidentReportLink:
    def test_construction(self) -> None:
        link = IncidentReportLink(
            incident_id=uuid.uuid4(),
            report_id=uuid.uuid4(),
            relationship=RelationshipType.DIRECT,
            linked_by="system",
        )
        assert link.reviewed_by is None


# ---------------------------------------------------------------------------
# LocationHypothesis
# ---------------------------------------------------------------------------


class TestLocationHypothesis:
    def _coords(self) -> PointCoordinates:
        return PointCoordinates(latitude=19.076, longitude=72.877)

    def test_probability_none_by_default(self) -> None:
        hyp = LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords())
        assert hyp.probability is None

    def test_probability_boundary_ok(self) -> None:
        LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords(), probability=0.0)
        LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords(), probability=1.0)

    def test_probability_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords(), probability=1.01)

    def test_uncertainty_radius_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            LocationHypothesis(
                incident_id=uuid.uuid4(),
                coordinates=self._coords(),
                uncertainty_radius_m=-1.0,
            )

    def test_default_verification_status(self) -> None:
        hyp = LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords())
        assert hyp.verification_status is VerificationStatus.UNVERIFIED

    def test_frozen(self) -> None:
        hyp = LocationHypothesis(incident_id=uuid.uuid4(), coordinates=self._coords())
        with pytest.raises((TypeError, ValidationError)):
            hyp.probability = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PriorityAssessment
# ---------------------------------------------------------------------------


class TestPriorityAssessment:
    def test_requires_human_review_defaults_true(self) -> None:
        pa = PriorityAssessment(priority=PriorityLevel.URGENT)
        assert pa.requires_human_review is True

    def test_reasons_are_tuple(self) -> None:
        pa = PriorityAssessment(priority=PriorityLevel.CRITICAL_REVIEW, reasons=("children present",))
        assert isinstance(pa.reasons, tuple)

    def test_unknown_fields_are_tuple(self) -> None:
        pa = PriorityAssessment(priority=PriorityLevel.STANDARD, unknown_fields=("medical_condition",))
        assert isinstance(pa.unknown_fields, tuple)

    def test_empty_defaults(self) -> None:
        pa = PriorityAssessment(priority=PriorityLevel.LOW)
        assert pa.reasons == ()
        assert pa.unknown_fields == ()

    def test_frozen(self) -> None:
        pa = PriorityAssessment(priority=PriorityLevel.URGENT)
        with pytest.raises((TypeError, ValidationError)):
            pa.priority = PriorityLevel.LOW  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Resource / Assignment / OperationEvent
# ---------------------------------------------------------------------------


class TestResource:
    def test_defaults(self) -> None:
        r = Resource(
            disaster_id=uuid.uuid4(),
            resource_type=ResourceType.BOAT,
            name="Rescue Boat 1",
        )
        assert r.availability_status is ResourceStatus.AVAILABLE
        assert r.location is None
        assert r.capacity is None

    def test_capacity_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            Resource(
                disaster_id=uuid.uuid4(),
                resource_type=ResourceType.SHELTER,
                name="Camp",
                capacity=0,
            )

    def test_with_location(self) -> None:
        loc = PointCoordinates(latitude=12.0, longitude=77.0)
        r = Resource(
            disaster_id=uuid.uuid4(),
            resource_type=ResourceType.MEDICAL_TEAM,
            name="Team Alpha",
            location=loc,
        )
        assert r.location == loc

    def test_frozen(self) -> None:
        r = Resource(
            disaster_id=uuid.uuid4(),
            resource_type=ResourceType.VEHICLE,
            name="Truck 1",
        )
        with pytest.raises((TypeError, ValidationError)):
            r.name = "changed"  # type: ignore[misc]


class TestAssignment:
    def test_defaults(self) -> None:
        a = Assignment(
            incident_id=uuid.uuid4(),
            resource_id=uuid.uuid4(),
            assigned_by=uuid.uuid4(),
        )
        assert a.status is AssignmentStatus.PROPOSED
        assert a.approved_at is None

    def test_id_auto_generated(self) -> None:
        did = uuid.uuid4()
        rid = uuid.uuid4()
        aid = uuid.uuid4()
        a1 = Assignment(incident_id=did, resource_id=rid, assigned_by=aid)
        a2 = Assignment(incident_id=did, resource_id=rid, assigned_by=aid)
        assert a1.id != a2.id

    def test_frozen(self) -> None:
        a = Assignment(
            incident_id=uuid.uuid4(),
            resource_id=uuid.uuid4(),
            assigned_by=uuid.uuid4(),
        )
        with pytest.raises((TypeError, ValidationError)):
            a.status = AssignmentStatus.APPROVED  # type: ignore[misc]


class TestOperationEvent:
    def test_defaults(self) -> None:
        ev = OperationEvent(
            incident_id=uuid.uuid4(),
            event_type=OperationEventType.PROPOSED,
        )
        assert ev.assignment_id is None
        assert ev.actor_id is None
        assert ev.notes is None
        assert ev.payload == {}

    def test_all_fields(self) -> None:
        inc_id = uuid.uuid4()
        asgn_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        ev = OperationEvent(
            incident_id=inc_id,
            assignment_id=asgn_id,
            event_type=OperationEventType.RESCUED,
            actor_id=actor_id,
            notes="all accounted for",
            payload={"count": 5},
        )
        assert ev.incident_id == inc_id
        assert ev.assignment_id == asgn_id
        assert ev.actor_id == actor_id
        assert ev.payload == {"count": 5}

    def test_frozen(self) -> None:
        ev = OperationEvent(incident_id=uuid.uuid4(), event_type=OperationEventType.CLOSED)
        with pytest.raises((TypeError, ValidationError)):
            ev.notes = "changed"  # type: ignore[misc]
