"""IVR Call Agent dialog state machine."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from raahat.application.ingestion.service import ReportIngestionService
from raahat.domain.reports.report import ReportSubmission
from raahat.infrastructure.speech import AudioInput, SpeechRecognizer

from .readback import (
    evaluate_readback_confirmation,
    extract_people_count_from_text,
    generate_number_readback_prompt,
)
from .session import IVRCallSession, IVRCallState
from .vad import EnergyVADDetector, VADDetector

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IVRTurnResult:
    """Outcome of one dialog turn with the caller."""

    prompt_text: str
    next_state: IVRCallState
    expect_input: str  # "audio", "dtmf", "any", "none"
    is_completed: bool
    submission: Optional[ReportSubmission] = None


class IVRCallAgent:
    """Orchestrates disaster distress IVR call turns.

    Enforces speech recognition with VAD, keypad fallback after recognition failures,
    number read-back confirmation for headcounts, and emits a structured ReportSubmission
    into ReportIngestionService. Never directly mutates incidents or assigns resources.
    """

    def __init__(
        self,
        speech_recognizer: SpeechRecognizer,
        vad_detector: Optional[VADDetector] = None,
        ingestion_service: Optional[ReportIngestionService] = None,
    ) -> None:
        self.speech_recognizer = speech_recognizer
        self.vad_detector = vad_detector or EnergyVADDetector()
        self.ingestion_service = ingestion_service

    async def handle_turn(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput] = None,
        dtmf_digits: Optional[str] = None,
    ) -> IVRTurnResult:
        """Process one conversational turn."""
        session.turn_count += 1
        if dtmf_digits:
            session.dtmf_history.append(dtmf_digits)

        # Enforce global turn cap
        if session.turn_count >= session.max_turns and session.current_state != IVRCallState.COMPLETED:
            logger.warning(
                "Turn cap reached for session %s; terminating and generating submission",
                session.call_sid,
            )
            session.current_state = IVRCallState.COMPLETED
            submission = session.to_submission()
            if self.ingestion_service:
                self.ingestion_service.ingest(submission)
            return IVRTurnResult(
                prompt_text="Dhanyawad. Aapki jankari darj kar li gayi hai.",
                next_state=IVRCallState.COMPLETED,
                expect_input="none",
                is_completed=True,
                submission=submission,
            )

        state = session.current_state

        if state == IVRCallState.INIT:
            session.current_state = IVRCallState.AWAITING_LOCATION
            return IVRTurnResult(
                prompt_text="Aap kahan phanse hain? Kripya apna sthan ya aas paas ka landmark batayein.",
                next_state=IVRCallState.AWAITING_LOCATION,
                expect_input="audio",
                is_completed=False,
            )

        if state == IVRCallState.AWAITING_LOCATION:
            return await self._handle_location(session, audio, dtmf_digits)

        if state == IVRCallState.AWAITING_LOCATION_KEYPAD:
            return self._handle_location_keypad(session, dtmf_digits)

        if state == IVRCallState.AWAITING_PEOPLE_COUNT:
            return await self._handle_people_count(session, audio, dtmf_digits)

        if state == IVRCallState.AWAITING_PEOPLE_COUNT_READBACK:
            return await self._handle_readback(session, audio, dtmf_digits)

        if state == IVRCallState.AWAITING_NEEDS:
            return await self._handle_needs(session, audio, dtmf_digits)

        # If already completed
        submission = session.to_submission()
        return IVRTurnResult(
            prompt_text="Aapka sandesh pehle hi darj ho chuka hai.",
            next_state=IVRCallState.COMPLETED,
            expect_input="none",
            is_completed=True,
            submission=submission,
        )

    # ------------------------------------------------------------------
    # Step handlers
    # ------------------------------------------------------------------

    async def _handle_location(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        if dtmf_digits:
            session.location_code_dtmf = dtmf_digits.strip()
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            return IVRTurnResult(
                prompt_text="Ward code darj ho gaya. Aapke saath kitne log hain? Sankhya batayein ya keypad par dabayein.",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="any",
                is_completed=False,
            )

        if audio is None or not self.vad_detector.detect_speech(audio):
            session.state_retries += 1
            if session.state_retries >= session.max_state_retries:
                session.current_state = IVRCallState.AWAITING_LOCATION_KEYPAD
                return IVRTurnResult(
                    prompt_text="Aapki aawaz nahi aayi. Kripya phone ke keypad par apna PIN code ya ward number dabayein.",
                    next_state=IVRCallState.AWAITING_LOCATION_KEYPAD,
                    expect_input="dtmf",
                    is_completed=False,
                )
            return IVRTurnResult(
                prompt_text="Kripya phir se batayein, aap kis jagah hain?",
                next_state=IVRCallState.AWAITING_LOCATION,
                expect_input="audio",
                is_completed=False,
            )

        transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
        session.transcripts.append(transcript)

        if transcript.confidence < session.low_confidence_threshold or not transcript.text.strip():
            session.state_retries += 1
            if session.state_retries >= session.max_state_retries:
                session.current_state = IVRCallState.AWAITING_LOCATION_KEYPAD
                return IVRTurnResult(
                    prompt_text="Aapki aawaz saaf nahi aayi. Kripya phone ke keypad par apna PIN code ya ward number dabayein.",
                    next_state=IVRCallState.AWAITING_LOCATION_KEYPAD,
                    expect_input="dtmf",
                    is_completed=False,
                )
            return IVRTurnResult(
                prompt_text="Aapki aawaz saaf nahi aayi. Kripya landmark ka naam phir se bolein.",
                next_state=IVRCallState.AWAITING_LOCATION,
                expect_input="audio",
                is_completed=False,
            )

        session.location_text = transcript.text.strip()
        session.state_retries = 0
        session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
        return IVRTurnResult(
            prompt_text="Sthan note kar liya gaya. Aapke saath kitne log hain? Sankhya batayein ya keypad par dabayein.",
            next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
            expect_input="any",
            is_completed=False,
        )

    def _handle_location_keypad(
        self,
        session: IVRCallSession,
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        if dtmf_digits and dtmf_digits.strip():
            session.location_code_dtmf = dtmf_digits.strip()
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            return IVRTurnResult(
                prompt_text="Code darj ho gaya. Aapke saath kitne log hain? Sankhya keypad par dabayein.",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="any",
                is_completed=False,
            )

        return IVRTurnResult(
            prompt_text="Kripya phone ke keypad par digits dabayein.",
            next_state=IVRCallState.AWAITING_LOCATION_KEYPAD,
            expect_input="dtmf",
            is_completed=False,
        )

    async def _handle_people_count(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        # 1. Unambiguous Keypad Entry
        if dtmf_digits and dtmf_digits.strip().isdigit():
            count = int(dtmf_digits.strip())
            session.people_count = count
            session.people_count_confirmed = True
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_NEEDS
            return IVRTurnResult(
                prompt_text=f"{count} log darj hue. Kis tarah ki madad chahiye? Jaise ki naav, doctor, ya bhojan?",
                next_state=IVRCallState.AWAITING_NEEDS,
                expect_input="audio",
                is_completed=False,
            )

        # 2. Spoken Audio Entry
        if audio is not None and self.vad_detector.detect_speech(audio):
            transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
            session.transcripts.append(transcript)
            extracted_count = extract_people_count_from_text(transcript.text)
            if extracted_count is not None:
                # Trigger read-back confirmation for spoken headcount!
                session.people_count_unconfirmed = extracted_count
                session.state_retries = 0
                session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT_READBACK
                readback_prompt = generate_number_readback_prompt(extracted_count, session.language_code)
                return IVRTurnResult(
                    prompt_text=readback_prompt,
                    next_state=IVRCallState.AWAITING_PEOPLE_COUNT_READBACK,
                    expect_input="any",
                    is_completed=False,
                )

        session.state_retries += 1
        if session.state_retries >= session.max_state_retries:
            return IVRTurnResult(
                prompt_text="Kripya keypad par sankhya dabayein (jaise 2 ya 4).",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="dtmf",
                is_completed=False,
            )

        return IVRTurnResult(
            prompt_text="Aapke saath kitne log hain? Kripya sankhya bolein ya keypad dabayein.",
            next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
            expect_input="any",
            is_completed=False,
        )

    async def _handle_readback(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        spoken_text: Optional[str] = None
        if audio is not None and self.vad_detector.detect_speech(audio):
            transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
            session.transcripts.append(transcript)
            spoken_text = transcript.text

        confirmed = evaluate_readback_confirmation(dtmf_digits, spoken_text)

        if confirmed is True:
            session.people_count = session.people_count_unconfirmed
            session.people_count_confirmed = True
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_NEEDS
            return IVRTurnResult(
                prompt_text="Pushti ho gayi. Kis tarah ki madad chahiye? Jaise ki naav, doctor, ya bhojan?",
                next_state=IVRCallState.AWAITING_NEEDS,
                expect_input="audio",
                is_completed=False,
            )

        if confirmed is False:
            session.people_count_unconfirmed = None
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            return IVRTurnResult(
                prompt_text="Theek hai. Kripya keypad par sahi sankhya dabayein.",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="dtmf",
                is_completed=False,
            )

        return IVRTurnResult(
            prompt_text="Pushti ke liye 1 dabayein ya Haan bolein. Sudhar ke liye 2 dabayein.",
            next_state=IVRCallState.AWAITING_PEOPLE_COUNT_READBACK,
            expect_input="any",
            is_completed=False,
        )

    async def _handle_needs(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        if audio is not None and self.vad_detector.detect_speech(audio):
            transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
            session.transcripts.append(transcript)
            session.situation_description = transcript.text.strip()

            text_lower = transcript.text.lower()
            if any(w in text_lower for w in ["naav", "boat"]):
                session.needs.append("boat")
            if any(w in text_lower for w in ["doctor", "dawa", "medical", "bimar"]):
                session.needs.append("medical")
            if any(w in text_lower for w in ["khana", "paani", "food", "water"]):
                session.needs.append("food_water")
        elif dtmf_digits:
            session.situation_description = f"DTMF Input: {dtmf_digits}"

        session.current_state = IVRCallState.COMPLETED
        submission = session.to_submission()

        # Submit to ingestion service if injected
        if self.ingestion_service:
            self.ingestion_service.ingest(submission)

        return IVRTurnResult(
            prompt_text="Aapka sandesh darj kar liya gaya hai. Bachav dal ko suchit kiya ja raha hai.",
            next_state=IVRCallState.COMPLETED,
            expect_input="none",
            is_completed=True,
            submission=submission,
        )
