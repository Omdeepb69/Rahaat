"""Fault injection tests for LLM unavailability, speech recognition crashes, operator disconnects, and reversible merge recovery."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest

from raahat.adapters.channels.ivr.agent import IVRCallAgent
from raahat.adapters.channels.ivr.session import IVRCallSession, IVRCallState
from raahat.application.dispatch.service import DispatchService
from raahat.application.incident_resolution.review import IncidentReviewService, LinkReviewAction
from raahat.domain.incidents.incident import PriorityLevel
from raahat.domain.operations.repository import InMemoryAssignmentRepository
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType
from raahat.domain.triage.facts import SeverityFacts
from raahat.infrastructure.database.models import IncidentModel
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.repositories.audit import InMemoryAuditRepository
from raahat.infrastructure.speech import AudioInput, SpeechRecognizer, Transcript


class CrashingSpeechRecognizer(SpeechRecognizer):
    """Recognizer that simulates an unexpected worker / subprocess crash."""

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript:
        raise RuntimeError("ASR worker process died unexpectedly (SIGSEGV in whisper backend)")


@pytest.mark.asyncio
async def test_speech_recognizer_crash_triggers_ivr_keypad_fallback() -> None:
    """Scenario: Speech recognition worker crashes during caller turn.

    The IVR agent must contain the exception, avoid dropping the call,
    and fall back to keypad DTMF input.
    """
    crashing_asr = CrashingSpeechRecognizer()
    agent = IVRCallAgent(speech_recognizer=crashing_asr)

    session = IVRCallSession(
        call_sid="CA-CRASH-TEST",
        disaster_id=uuid.uuid4(),
        caller_phone="+919876543210",
        current_state=IVRCallState.AWAITING_LOCATION,
    )

    audio = AudioInput(audio_bytes=b"\x00" * 3200, sample_rate=16000)

    # Turn 1: Recognizer crashes — session.state_retries increments to 1
    res1 = await agent.handle_turn(session, audio=audio)
    # Session state machine handles failure and prompts retry
    assert session.state_retries == 1
    assert res1.next_state == IVRCallState.AWAITING_LOCATION

    # Turn 2: Second failure reaches max_state_retries (default=2), triggers keypad fallback
    res2 = await agent.handle_turn(session, audio=audio)
    assert session.state_retries >= 2
    assert res2.next_state == IVRCallState.AWAITING_LOCATION_KEYPAD
    assert "keypad" in res2.prompt_text.lower()
    assert res2.expect_input == "dtmf"


def test_llm_unavailability_preserves_safe_triage_priority() -> None:
    """Scenario: LLM fact extraction service is completely unreachable / times out.

    Deterministic triage policy must evaluate safely under unknown observations
    without ever downgrading priority or assuming absence of danger.
    """
    from raahat.policies.triage import DeterministicSafetyPriorityPolicy

    policy = DeterministicSafetyPriorityPolicy()

    # Deep rising water reported, but trapped occupants and medical need are UNKNOWN (LLM failed)
    facts_with_llm_outage = SeverityFacts(
        water_depth_cm=180.0,  # Deep flood
        water_level_trend="rising",
        trapped_status=None,  # UNKNOWN due to LLM timeout
        medical_emergency=None,  # UNKNOWN due to LLM timeout
        vulnerable_present=None,  # UNKNOWN
        unknown_fields=("trapped_status", "medical_emergency", "vulnerable_present"),
    )

    assessment = policy.assess(facts_with_llm_outage)

    # Must NOT drop to standard/low just because trapped count is unknown
    assert assessment.priority in (PriorityLevel.CRITICAL_REVIEW, PriorityLevel.URGENT)
    # Unknown fields must be explicitly preserved
    assert "trapped_status" in assessment.unknown_fields
    assert "medical_emergency" in assessment.unknown_fields
    assert "deep_rising_flood_with_unknown_occupants" in assessment.reasons


def test_operator_disconnect_preserves_durable_assignment_state() -> None:
    """Scenario: Operator proposes a rescue assignment and disconnects.

    State must remain durably persisted so a second operator can approve it.
    """
    assignment_repo = InMemoryAssignmentRepository()
    audit_repo = InMemoryAuditRepository()
    dispatch_service = DispatchService(
        assignment_repo=assignment_repo,
        audit_repo=audit_repo,
    )

    incident_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    dispatcher_1 = uuid.uuid4()
    dispatcher_2 = uuid.uuid4()

    # Operator 1 proposes assignment; returns (Assignment, OperationEvent) tuple
    assignment, _propose_event = dispatch_service.propose_assignment(
        incident_id=incident_id,
        resource_id=resource_id,
        dispatcher_id=dispatcher_1,
        notes="Proposed by primary operator before disconnection",
    )
    assert assignment.status == AssignmentStatus.PROPOSED

    # Operator 1 DISCONNECTS / browser closes

    # Operator 2 logs in on a different machine, inspects existing assignments
    existing_assignments = dispatch_service.list_assignments(incident_id)
    assert len(existing_assignments) == 1
    found = existing_assignments[0]
    assert found.id == assignment.id
    assert found.status == AssignmentStatus.PROPOSED

    # Operator 2 approves deployment; record_event returns (Assignment, OperationEvent) tuple
    updated_assignment, event = dispatch_service.record_event(
        assignment_id=assignment.id,
        event_type=OperationEventType.APPROVED,
        actor_id=dispatcher_2,
        notes="Approved by secondary command operator",
    )
    assert event.event_type.value == "approved"

    # Updated status reflected durably
    updated = assignment_repo.get_by_id(assignment.id)
    assert updated is not None
    assert updated.status == AssignmentStatus.APPROVED
    assert updated.approved_at is not None


def test_reversible_unmerge_recovers_from_human_linking_error() -> None:
    """Scenario: Dispatcher mistakenly approves an incident merge link.

    The system must support reversible unmerge: reopening source incident,
    detaching IncidentReportModel links, and retaining audit events with zero data destruction.
    """
    mock_session_factory = MagicMock()
    mock_session = MagicMock()
    mock_session_factory.return_value.__enter__.return_value = mock_session

    audit_repo = InMemoryAuditRepository()
    service = IncidentReviewService(session_factory=mock_session_factory, audit_repo=audit_repo)

    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    merge_event_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()

    # Active merge event in DB
    merge_event = EntityMergeEventModel(
        id=merge_event_id,
        source_entity_type="incident",
        source_entity_id=source_id,
        target_entity_type="incident",
        target_entity_id=target_id,
        reviewed_by=dispatcher_id,
        reason="Erroneous duplicate merge",
        status="active",
        created_at=datetime.now(timezone.utc),
    )

    source_incident = IncidentModel(id=source_id, status="merged")

    # _unmerge makes multiple session.scalars() calls:
    #   1st: select(EntityMergeEventModel) → returns merge_event via .first()
    #   2nd: select(IncidentReportModel) → returns [] via .all() (no reports to unlink)
    #   3rd: select(IncidentLinkModel) → returns None via .first() (no link to revert)
    merge_event_result = MagicMock()
    merge_event_result.first.return_value = merge_event

    no_reports_result = MagicMock()
    no_reports_result.all.return_value = []

    no_link_result = MagicMock()
    no_link_result.first.return_value = None

    mock_session.scalars.side_effect = [
        merge_event_result,
        no_reports_result,
        no_link_result,
    ]

    # _unmerge also calls session.get(IncidentModel, source_id) to reopen the source
    mock_session.get.side_effect = lambda model_cls, pk: {
        (IncidentModel, source_id): source_incident,
    }.get((model_cls, pk))

    # Dispatcher initiates unmerge
    result = service.review_link(
        source_incident_id=source_id,
        target_incident_id=target_id,
        action=LinkReviewAction.UNMERGE,
        dispatcher_id=dispatcher_id,
        reason="Reversing mistaken merge",
        merge_event_id=merge_event_id,
    )

    assert result.status == "reversed"
    assert result.source_incident_id == source_id
    assert merge_event.status == "reversed"

    # Verify tamper-evident audit record was logged
    audit_events = audit_repo.get_entity_chain("incident", target_id)
    assert len(audit_events) == 1
    assert audit_events[0].action == "incident.unmerged"
