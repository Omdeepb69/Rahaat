"""Unit tests for IncidentResolutionService orchestration using InMemoryIncidentRepository."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from raahat.application.incident_resolution.matcher import ConservativeIncidentMatcher
from raahat.application.incident_resolution.models import (
    IncidentSnapshot,
    ResolutionDecisionType,
)
from raahat.application.incident_resolution.resolver import ConservativeIncidentResolver
from raahat.application.incident_resolution.service import IncidentResolutionService
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.incidents.incident import Incident
from raahat.domain.incidents.repository import InMemoryIncidentRepository
from raahat.domain.reports.report import Report
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import (
    ProcessingStatus,
    SourceType,
    VerificationStatus,
)


def _make_report(
    payload: dict,
    disaster_id: uuid.UUID,
    phone: str | None = None,
) -> Report:
    return Report(
        id=uuid.uuid4(),
        disaster_id=disaster_id,
        source_type=SourceType.WEB,
        source_identity=phone,
        raw_payload=payload,
        received_at=datetime.now(timezone.utc),
        client_created_at=datetime.now(timezone.utc),
        idempotency_key=f"rep-{uuid.uuid4().hex}",
        processing_status=ProcessingStatus.PENDING,
    )


class TestIncidentResolutionServiceInMemory:
    def test_auto_link_attaches_report_to_existing_incident(self) -> None:
        disaster_id = uuid.uuid4()
        existing_inc_id = uuid.uuid4()
        existing_inc = Incident(id=existing_inc_id, disaster_id=disaster_id)

        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=existing_inc_id,
            coordinates=PointCoordinates(latitude=18.5200, longitude=73.8500),
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )
        existing_report = _make_report({}, disaster_id=disaster_id, phone="+919876543210")

        snapshot = IncidentSnapshot(
            incident=existing_inc,
            hypotheses=[hyp],
            reports=[existing_report],
        )

        repo = InMemoryIncidentRepository()
        repo.save(existing_inc)

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        resolver = ConservativeIncidentResolver(auto_link_threshold=0.80)
        service = IncidentResolutionService(
            matcher=matcher,
            resolver=resolver,
            incident_repo=repo,
        )

        incoming_report = _make_report(
            payload={"latitude": 18.5201, "longitude": 73.8501},
            disaster_id=disaster_id,
            phone="+919876543210",
        )

        result = service.resolve_report(incoming_report)

        assert result.decision.decision_type == ResolutionDecisionType.AUTO_LINK
        assert result.is_new_incident is False
        assert result.incident_id == existing_inc_id
        assert result.link_id is None

        # Verify repo has the report link
        linked_reports = repo.list_reports_for_incident(existing_inc_id)
        assert incoming_report.id in linked_reports

    def test_ambiguous_match_creates_incident_and_pending_review_link(self) -> None:
        disaster_id = uuid.uuid4()
        existing_inc_id = uuid.uuid4()
        existing_inc = Incident(id=existing_inc_id, disaster_id=disaster_id)

        # Distance is 120m away, but differing phone -> ambiguous score in [0.40, 0.80)
        hyp = LocationHypothesis(
            id=uuid.uuid4(),
            incident_id=existing_inc_id,
            coordinates=PointCoordinates(latitude=18.5200, longitude=73.8500),
            candidate_label="pin",
            verification_status=VerificationStatus.CONFIRMED,
        )
        existing_report = _make_report({}, disaster_id=disaster_id, phone="+911111122222")

        snapshot = IncidentSnapshot(
            incident=existing_inc,
            hypotheses=[hyp],
            reports=[existing_report],
        )

        repo = InMemoryIncidentRepository()
        repo.save(existing_inc)

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [snapshot])
        resolver = ConservativeIncidentResolver(auto_link_threshold=0.80, review_threshold=0.40)
        service = IncidentResolutionService(
            matcher=matcher,
            resolver=resolver,
            incident_repo=repo,
        )

        # Incoming report with different phone, nearby coordinates
        incoming_report = _make_report(
            payload={"latitude": 18.5208, "longitude": 73.8505},
            disaster_id=disaster_id,
            phone="+919876543210",
        )

        result = service.resolve_report(incoming_report)

        assert result.decision.decision_type == ResolutionDecisionType.REQUIRES_REVIEW
        assert result.is_new_incident is True
        assert result.incident_id != existing_inc_id
        assert result.link_id is not None

        # Verify new incident created in repo
        new_inc = repo.get_by_id(result.incident_id)
        assert new_inc is not None

        # Verify pending_review link created in repo
        links = repo.list_links_for_incident(result.incident_id)
        assert len(links) == 1
        link = links[0]
        assert link.id == result.link_id
        assert link.incident_a_id == result.incident_id
        assert link.incident_b_id == existing_inc_id
        assert link.status == "pending_review"

    def test_no_candidates_creates_independent_incident(self) -> None:
        disaster_id = uuid.uuid4()
        repo = InMemoryIncidentRepository()

        matcher = ConservativeIncidentMatcher(snapshot_provider=lambda d_id: [])
        resolver = ConservativeIncidentResolver()
        service = IncidentResolutionService(
            matcher=matcher,
            resolver=resolver,
            incident_repo=repo,
        )

        incoming_report = _make_report({"text": "isolated report"}, disaster_id=disaster_id)
        result = service.resolve_report(incoming_report)

        assert result.decision.decision_type == ResolutionDecisionType.CREATE_NEW
        assert result.is_new_incident is True
        assert result.link_id is None

        # Verify new incident saved and report linked
        new_inc = repo.get_by_id(result.incident_id)
        assert new_inc is not None
        assert incoming_report.id in repo.list_reports_for_incident(result.incident_id)
