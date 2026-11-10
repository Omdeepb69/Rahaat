"""Unit tests for IVR channel adapter, session state machine, and fallbacks."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from raahat.adapters.channels.ivr import (
    IVRCallAgent,
    IVRCallSession,
    IVRCallState,
    evaluate_readback_confirmation,
    extract_people_count_from_text,
    generate_number_readback_prompt,
)
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.speech import AudioInput, MockSpeechRecognizer


def _make_dummy_audio(text: str) -> AudioInput:
    """Helper creating mock AudioInput with encoded text for MockSpeechRecognizer."""
    return AudioInput(audio_bytes=text.encode("utf-8"), sample_rate=16000)


def _make_silent_audio() -> AudioInput:
    """Helper creating silent audio bytes (zeros)."""
    return AudioInput(audio_bytes=b"\x00" * 3200, sample_rate=16000)


class TestReadbackHelpers:
    def test_extract_people_count_digits(self) -> None:
        assert extract_people_count_from_text("we are 4 people trapped") == 4
        assert extract_people_count_from_text("total 12 members") == 12
        assert extract_people_count_from_text("5") == 5

    def test_extract_people_count_hindi_words(self) -> None:
        assert extract_people_count_from_text("hum teen log hain") == 3
        assert extract_people_count_from_text("yahan paanch vyakti hain") == 5
        assert extract_people_count_from_text("das log phanse hain") == 10

    def test_extract_people_count_english_words(self) -> None:
        assert extract_people_count_from_text("there are two children") == 2
        assert extract_people_count_from_text("seven people on roof") == 7

    def test_extract_people_count_none_found(self) -> None:
        assert extract_people_count_from_text("paani bahut jyada hai") is None

    def test_readback_prompt_generation(self) -> None:
        hindi = generate_number_readback_prompt(5, "hi")
        assert "5 vyakti" in hindi
        assert "1 dabayein" in hindi

        eng = generate_number_readback_prompt(3, "en")
        assert "3 people" in eng
        assert "Press 1" in eng

    def test_evaluate_readback_dtmf(self) -> None:
        assert evaluate_readback_confirmation(dtmf_digits="1") is True
        assert evaluate_readback_confirmation(dtmf_digits="2") is False
        assert evaluate_readback_confirmation(dtmf_digits="9") is None

    def test_evaluate_readback_speech(self) -> None:
        assert evaluate_readback_confirmation(spoken_text="haan sahi hai") is True
        assert evaluate_readback_confirmation(spoken_text="yes confirmed") is True
        assert evaluate_readback_confirmation(spoken_text="nahi galat hai") is False
        assert evaluate_readback_confirmation(spoken_text="no change it") is False
        assert evaluate_readback_confirmation(spoken_text="kya bola aapne") is None


class TestIVRCallAgent:
    @pytest.mark.asyncio
    async def test_full_speech_dialog_flow(self) -> None:
        disaster_id = uuid.uuid4()
        session = IVRCallSession(
            call_sid="CA123456789",
            disaster_id=disaster_id,
            caller_phone="+919876543210",
        )

        recognizer = MockSpeechRecognizer()
        # Mock VAD that detects speech on any non-empty audio
        vad = MagicMock()
        vad.detect_speech.return_value = True

        mock_ingestion = MagicMock()
        agent = IVRCallAgent(
            speech_recognizer=recognizer,
            vad_detector=vad,
            ingestion_service=mock_ingestion,
        )

        # Turn 1: Init -> Awaiting Location
        r1 = await agent.handle_turn(session)
        assert r1.next_state == IVRCallState.AWAITING_LOCATION
        assert "kahan phanse hain" in r1.prompt_text.lower()
        assert r1.is_completed is False

        # Turn 2: Location answered via speech
        recognizer.queue_transcript("Shiv Mandir ke paas Ward 5", confidence=0.92)
        r2 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))
        assert r2.next_state == IVRCallState.AWAITING_PEOPLE_COUNT
        assert session.location_text == "Shiv Mandir ke paas Ward 5"
        assert "kitne log" in r2.prompt_text.lower()

        # Turn 3: Headcount answered via speech ("chaar log" -> 4)
        recognizer.queue_transcript("Hum chaar log hain", confidence=0.90)
        r3 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))
        assert r3.next_state == IVRCallState.AWAITING_PEOPLE_COUNT_READBACK
        assert session.people_count_unconfirmed == 4
        assert "4 vyakti" in r3.prompt_text

        # Turn 4: Read-back confirmed via speech ("haan sahi hai")
        recognizer.queue_transcript("Haan ji haan", confidence=0.95)
        r4 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))
        assert r4.next_state == IVRCallState.AWAITING_NEEDS
        assert session.people_count == 4
        assert session.people_count_confirmed is True
        assert "madad" in r4.prompt_text.lower()

        # Turn 5: Needs answered via speech ("naav chahiye aur doctor")
        recognizer.queue_transcript("Ghar me paani bhar gaya hai naav bhejo aur doctor chahiye", confidence=0.90)
        r5 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))
        assert r5.next_state == IVRCallState.COMPLETED
        assert r5.is_completed is True
        assert r5.submission is not None

        # Verify submission contents
        sub = r5.submission
        assert sub.disaster_id == disaster_id
        assert sub.source_type == SourceType.IVR
        assert sub.source_identity == "+919876543210"
        assert sub.source_event_id == "CA123456789"
        assert sub.idempotency_key == "ivr-CA123456789"
        assert sub.raw_payload["location_text"] == "Shiv Mandir ke paas Ward 5"
        assert sub.raw_payload["people_count"] == 4
        assert sub.raw_payload["people_count_confirmed"] is True
        assert "boat" in sub.raw_payload["needs"]
        assert "medical" in sub.raw_payload["needs"]

        # Verify ingestion service was called atomically
        mock_ingestion.ingest.assert_called_once_with(sub)

    @pytest.mark.asyncio
    async def test_keypad_fallback_on_repeated_low_confidence(self) -> None:
        session = IVRCallSession(
            call_sid="CA-FALLBACK-01",
            disaster_id=uuid.uuid4(),
            caller_phone="+919999900000",
            max_state_retries=2,
            low_confidence_threshold=0.6,
        )

        recognizer = MockSpeechRecognizer()
        vad = MagicMock()
        vad.detect_speech.return_value = True

        agent = IVRCallAgent(speech_recognizer=recognizer, vad_detector=vad)

        # Turn 1: Init
        await agent.handle_turn(session)
        assert session.current_state == IVRCallState.AWAITING_LOCATION

        # Turn 2: Low confidence speech attempt 1 (< 0.6)
        recognizer.queue_transcript("garbled static", confidence=0.25)
        r2 = await agent.handle_turn(session, audio=_make_dummy_audio("bad"))
        assert r2.next_state == IVRCallState.AWAITING_LOCATION
        assert session.state_retries == 1

        # Turn 3: Low confidence speech attempt 2 -> triggers KEYPAD FALLBACK!
        recognizer.queue_transcript("more noise", confidence=0.30)
        r3 = await agent.handle_turn(session, audio=_make_dummy_audio("bad"))
        assert r3.next_state == IVRCallState.AWAITING_LOCATION_KEYPAD
        assert "keypad par apna pin code ya ward number" in r3.prompt_text.lower()
        assert r3.expect_input == "dtmf"

        # Turn 4: Caller enters PIN code on keypad: "403101"
        r4 = await agent.handle_turn(session, dtmf_digits="403101")
        assert r4.next_state == IVRCallState.AWAITING_PEOPLE_COUNT
        assert session.location_code_dtmf == "403101"

    @pytest.mark.asyncio
    async def test_direct_keypad_dtmf_for_headcount_bypasses_readback(self) -> None:
        session = IVRCallSession(
            call_sid="CA-DTMF-02",
            disaster_id=uuid.uuid4(),
            caller_phone="+919876543210",
            current_state=IVRCallState.AWAITING_PEOPLE_COUNT,
        )
        recognizer = MockSpeechRecognizer()
        agent = IVRCallAgent(speech_recognizer=recognizer)

        # Caller presses "6" on phone keypad
        r = await agent.handle_turn(session, dtmf_digits="6")

        # DTMF digit is unambiguous: directly sets confirmed count and proceeds to needs!
        assert r.next_state == IVRCallState.AWAITING_NEEDS
        assert session.people_count == 6
        assert session.people_count_confirmed is True

    @pytest.mark.asyncio
    async def test_readback_rejection_allows_correction(self) -> None:
        session = IVRCallSession(
            call_sid="CA-REJECT-03",
            disaster_id=uuid.uuid4(),
            caller_phone="+919876543210",
            current_state=IVRCallState.AWAITING_PEOPLE_COUNT_READBACK,
            people_count_unconfirmed=10,
        )
        recognizer = MockSpeechRecognizer()
        agent = IVRCallAgent(speech_recognizer=recognizer)

        # Caller presses DTMF "2" (rejects readback 10)
        r1 = await agent.handle_turn(session, dtmf_digits="2")
        assert r1.next_state == IVRCallState.AWAITING_PEOPLE_COUNT
        assert session.people_count_unconfirmed is None

        # Caller re-enters "3" on keypad
        r2 = await agent.handle_turn(session, dtmf_digits="3")
        assert r2.next_state == IVRCallState.AWAITING_NEEDS
        assert session.people_count == 3
        assert session.people_count_confirmed is True

    @pytest.mark.asyncio
    async def test_turn_cap_terminates_gracefully(self) -> None:
        session = IVRCallSession(
            call_sid="CA-TURNCAP-04",
            disaster_id=uuid.uuid4(),
            caller_phone="+919876543210",
            max_turns=2,
        )
        recognizer = MockSpeechRecognizer()
        agent = IVRCallAgent(speech_recognizer=recognizer)

        # Turn 1
        await agent.handle_turn(session)
        # Turn 2 reaches max_turns
        r2 = await agent.handle_turn(session)

        assert r2.is_completed is True
        assert r2.next_state == IVRCallState.COMPLETED
        assert r2.submission is not None

    @pytest.mark.asyncio
    async def test_unresolvable_location_triggers_reprompt(self) -> None:
        """When an unseeded location has zero hits, agent reprompts for nearby landmarks."""
        from unittest.mock import AsyncMock
        from raahat.application.location.models import ClarificationQuestion, LocationResolution

        disaster_id = uuid.uuid4()
        session = IVRCallSession(
            call_sid="CA-UNRESOLVED-01",
            disaster_id=disaster_id,
            caller_phone="+919876543210",
            current_state=IVRCallState.AWAITING_LOCATION,
        )

        recognizer = MockSpeechRecognizer()
        vad = MagicMock()
        vad.detect_speech.return_value = True

        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(
            return_value=LocationResolution(
                hypotheses=[],
                uncertainty_radius_m=5000.0,
                clarification_question=ClarificationQuestion(
                    prompt_text="Aapka sthan confirm nahi ho paaya. Kripya apna ward number batayein.",
                    question_type="general",
                ),
                resolved_landmark=None,
            )
        )

        agent = IVRCallAgent(
            speech_recognizer=recognizer,
            vad_detector=vad,
            location_resolver=mock_resolver,
        )

        # Turn: Caller gives unrecognized location "Ghar ke paas"
        recognizer.queue_transcript("Ghar ke paas", confidence=0.92)
        r = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))

        # Agent stays in AWAITING_LOCATION and asks caller for nearby hospital/station/main road
        assert r.next_state == IVRCallState.AWAITING_LOCATION
        assert "map par nahi mila" in r.prompt_text.lower()
        assert session.location_resolved is False
        assert session.location_unresolvable_attempts == 1

    @pytest.mark.asyncio
    async def test_multiple_candidates_triggers_disambiguation_question(self) -> None:
        """When location matches multiple landmarks, agent asks optimal disambiguation question."""
        from unittest.mock import AsyncMock
        from raahat.application.location.models import ClarificationQuestion, LocationResolution
        from raahat.domain.geospatial.landmark import Landmark
        from raahat.domain.shared.coordinates import PointCoordinates

        disaster_id = uuid.uuid4()
        session = IVRCallSession(
            call_sid="CA-AMBIGUOUS-02",
            disaster_id=disaster_id,
            caller_phone="+919876543210",
            current_state=IVRCallState.AWAITING_LOCATION,
        )

        recognizer = MockSpeechRecognizer()
        vad = MagicMock()
        vad.detect_speech.return_value = True

        mock_resolver = MagicMock()
        # Turn 1 resolution: ambiguous candidates; Turn 2: resolved
        mock_resolver.resolve = AsyncMock(
            side_effect=[
                LocationResolution(
                    hypotheses=[],
                    uncertainty_radius_m=1200.0,
                    clarification_question=ClarificationQuestion(
                        prompt_text="Kya aap Shiva Temple (Ward 2) ke paas hain ya Shiva Temple (Ward 7) ke paas?",
                        question_type="disambiguation",
                        options=["Shiva Temple (Ward 2)", "Shiva Temple (Ward 7)"],
                    ),
                    resolved_landmark=None,
                ),
                LocationResolution(
                    hypotheses=[],
                    uncertainty_radius_m=150.0,
                    clarification_question=None,
                    resolved_landmark=Landmark(
                        id=uuid.uuid4(),
                        name="Shiva Temple (Ward 2)",
                        kind="temple",
                        location=PointCoordinates(latitude=10.1, longitude=76.3),
                        salience=0.9,
                    ),
                ),
            ]
        )

        agent = IVRCallAgent(
            speech_recognizer=recognizer,
            vad_detector=vad,
            location_resolver=mock_resolver,
        )

        # Turn 1: Caller says "Shiva Temple"
        recognizer.queue_transcript("Shiva Temple", confidence=0.95)
        r1 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))

        assert r1.next_state == IVRCallState.AWAITING_LOCATION_CLARIFICATION
        assert "ward 2" in r1.prompt_text.lower()
        assert session.current_state == IVRCallState.AWAITING_LOCATION_CLARIFICATION

        # Turn 2: Caller chooses option 1 ("Ward 2")
        recognizer.queue_transcript("Ward 2", confidence=0.95)
        r2 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))

        assert r2.next_state == IVRCallState.AWAITING_PEOPLE_COUNT
        assert session.location_resolved is True
        assert "shiva temple" in session.location_text.lower()

    @pytest.mark.asyncio
    async def test_safety_probe_injected_before_completion_when_water_hazard(self) -> None:
        """When water hazard is present without depth or vulnerability, agent probes for P0 details."""
        disaster_id = uuid.uuid4()
        session = IVRCallSession(
            call_sid="CA-PROBE-03",
            disaster_id=disaster_id,
            caller_phone="+919876543210",
            current_state=IVRCallState.AWAITING_LOCATION,
        )

        recognizer = MockSpeechRecognizer()
        vad = MagicMock()
        vad.detect_speech.return_value = True
        mock_ingestion = MagicMock()

        agent = IVRCallAgent(
            speech_recognizer=recognizer,
            vad_detector=vad,
            ingestion_service=mock_ingestion,
        )

        # Turn 1: Caller states location + mentions water rising fast
        recognizer.queue_transcript("Aluva Shiva Temple paani badh raha hai jaldi aao", confidence=0.95)
        r1 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))
        assert session.water_hazard_detected is True
        assert r1.next_state == IVRCallState.AWAITING_PEOPLE_COUNT

        # Turn 2: Headcount via keypad (5 people)
        r2 = await agent.handle_turn(session, dtmf_digits="5")
        assert session.people_count == 5
        assert r2.next_state == IVRCallState.AWAITING_NEEDS

        # Turn 3: Needs answered ("naav chahiye")
        recognizer.queue_transcript("Sirf naav chahiye", confidence=0.92)
        r3 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))

        # Safety probe is injected because depth / vulnerability was not yet answered!
        assert r3.next_state == IVRCallState.AWAITING_SAFETY_PROBE
        assert r3.is_completed is False
        assert "paani kitna gehra hai" in r3.prompt_text.lower()

        # Turn 4: Caller answers safety probe
        recognizer.queue_transcript("Gale tak paani hai aur bujurg dadi bimar hain", confidence=0.93)
        r4 = await agent.handle_turn(session, audio=_make_dummy_audio("anything"))

        assert r4.next_state == IVRCallState.COMPLETED
        assert r4.is_completed is True
        assert session.safety_probe_answered is True
        assert "medical" in session.needs
        assert "Safety Probe" in session.situation_description
        mock_ingestion.ingest.assert_called_once()
