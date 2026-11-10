"""IVR Call Agent dialog state machine with dynamic LLM disaster reasoning."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from raahat.application.ingestion.service import ReportIngestionService
from raahat.application.location import (
    ClarificationAnswer,
    LocationObservation,
    PostGISGazetteerResolver,
)
from raahat.domain.reports.report import ReportSubmission
from raahat.infrastructure.llm import (
    EmergencyFactExtraction,
    LLMClient,
    create_llm_client,
)
from raahat.infrastructure.speech import AudioInput, SpeechRecognizer

from .readback import (
    evaluate_readback_confirmation,
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
    extraction: Optional[EmergencyFactExtraction] = None


class IVRCallAgent:
    """Orchestrates disaster distress IVR call turns with dynamic LLM reasoning.

    Listens to caller speech via ASR, understands entities (location, people count,
    hazards, medical needs) adaptively using the LLM reasoning client, asks only
    for missing details, and initiates dispatch immediately once critical safety
    facts are gathered.
    """

    def __init__(
        self,
        speech_recognizer: SpeechRecognizer,
        vad_detector: Optional[VADDetector] = None,
        ingestion_service: Optional[ReportIngestionService] = None,
        llm_client: Optional[LLMClient] = None,
        location_resolver: Optional[PostGISGazetteerResolver] = None,
    ) -> None:
        self.speech_recognizer = speech_recognizer
        self.vad_detector = vad_detector or EnergyVADDetector()
        self.ingestion_service = ingestion_service
        self.llm_client = llm_client or create_llm_client()
        self.location_resolver = location_resolver

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

        # Initial turn (Greeting prompt)
        if state == IVRCallState.INIT:
            session.current_state = IVRCallState.AWAITING_LOCATION
            return IVRTurnResult(
                prompt_text="Namaste. Raahat aapatkalin helpline. Aap kahan phanse hain aur sthiti kya hai? Kripya sthan ya landmark batayein.",
                next_state=IVRCallState.AWAITING_LOCATION,
                expect_input="audio",
                is_completed=False,
            )

        # Specialized keypad & readback states
        if state == IVRCallState.AWAITING_LOCATION_KEYPAD:
            return self._handle_location_keypad(session, dtmf_digits)

        if state == IVRCallState.AWAITING_PEOPLE_COUNT_READBACK:
            return await self._handle_readback(session, audio, dtmf_digits)

        if state == IVRCallState.AWAITING_LOCATION_CLARIFICATION:
            return await self._handle_location_clarification(session, audio, dtmf_digits)

        if state == IVRCallState.AWAITING_SAFETY_PROBE:
            return await self._handle_safety_probe(session, audio, dtmf_digits)

        # Keypad DTMF entry when digits supplied without audio
        if dtmf_digits and not audio:
            return await self._handle_dtmf_input(session, dtmf_digits)

        # Voice audio / spoken input handling with dynamic LLM reasoning
        return await self._handle_spoken_turn(session, audio, dtmf_digits)

    # ------------------------------------------------------------------
    # Dynamic Spoken Turn & LLM Reasoning
    # ------------------------------------------------------------------

    async def _handle_spoken_turn(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        # 1. Voice activity detection
        if audio is None or not self.vad_detector.detect_speech(audio):
            session.state_retries += 1
            if session.state_retries >= session.max_state_retries:
                if session.current_state == IVRCallState.AWAITING_LOCATION:
                    session.current_state = IVRCallState.AWAITING_LOCATION_KEYPAD
                    return IVRTurnResult(
                        prompt_text="Aapki aawaz nahi aayi. Kripya phone ke keypad par apna PIN code ya ward number dabayein.",
                        next_state=IVRCallState.AWAITING_LOCATION_KEYPAD,
                        expect_input="dtmf",
                        is_completed=False,
                    )
                else:
                    return IVRTurnResult(
                        prompt_text="Kripya keypad par sankhya dabayein.",
                        next_state=session.current_state,
                        expect_input="dtmf",
                        is_completed=False,
                    )
            return IVRTurnResult(
                prompt_text="Kripya phir se batayein, aap kis jagah hain aur kitne log hain?",
                next_state=session.current_state,
                expect_input="audio",
                is_completed=False,
            )

        # 2. Speech transcription via SpeechRecognizer (Prisma / Whisper / Mock)
        transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
        session.transcripts.append(transcript)

        spoken_text = transcript.text.strip()
        if transcript.confidence < session.low_confidence_threshold or not spoken_text:
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
                prompt_text="Aapki aawaz saaf nahi aayi. Kripya sthan aur sthiti phir se bolein.",
                next_state=session.current_state,
                expect_input="audio",
                is_completed=False,
            )

        # 3. Dynamic LLM Reasoning & Entity Extraction
        current_facts = {
            "location_text": session.location_text,
            "people_count": session.people_count,
            "needs": list(session.needs),
            "medical_urgency": "medical" in session.needs,
        }
        history = [{"role": "caller", "content": t.text} for t in session.transcripts[:-1]]

        extraction = await self.llm_client.extract_and_respond(
            dialog_history=history,
            current_facts=current_facts,
            latest_user_utterance=spoken_text,
            language_code=session.language_code,
        )

        # 4. Integrate extracted knowledge into session
        if extraction.location_text:
            session.location_text = extraction.location_text
        if extraction.needs:
            for n in extraction.needs:
                if n not in session.needs:
                    session.needs.append(n)
        if extraction.situation_summary:
            session.situation_description = extraction.situation_summary

        water_hazards = {"water_rising_fast", "submerged", "trapped_roof", "drowning_risk"}
        if any(h in water_hazards for h in extraction.hazards) or any(
            w in spoken_text.lower()
            for w in ["paani badh", "water rising", "gale tak paani", "chhat par", "submerged", "drowning"]
        ):
            session.water_hazard_detected = True

        # Check if caller already provided depth or vulnerable details across transcripts
        combined_text = " ".join(t.text.lower() for t in session.transcripts)
        has_depth = bool(
            re.search(r"\b\d+\s*(?:feet|foot|ft|meter|mtr|inch|floor|manzil)\b", combined_text)
            or any(w in combined_text for w in ["gale tak", "kamar tak", "chhat tak", "chest deep", "deep"])
        )
        has_vulnerability = any(
            w in combined_text
            for w in ["elderly", "bujurg", "vriddh", "pregnant", "garbhwati", "bachha", "child", "infant", "bimar", "sick", "bedridden"]
        )
        if has_depth or has_vulnerability:
            session.safety_probe_answered = True

        session.state_retries = 0

        # Spatial Grounding: verify location against PostGIS gazetteer if resolver configured
        if self.location_resolver is not None and session.location_text and not session.location_resolved:
            obs_answers = [
                ClarificationAnswer(
                    question_id=a["question_id"],
                    selected_option=a.get("selected_option"),
                    text_response=a.get("text_response"),
                )
                for a in session.clarification_answers
            ]
            loc_obs = LocationObservation(
                incident_id=session.disaster_id,
                raw_text=session.location_text,
                answers=obs_answers,
            )
            loc_res = await self.location_resolver.resolve(loc_obs)

            if loc_res.resolved_landmark is not None:
                session.location_resolved = True
                session.location_unresolvable_attempts = 0
            elif (
                loc_res.clarification_question
                and loc_res.clarification_question.question_type == "disambiguation"
            ):
                session.current_state = IVRCallState.AWAITING_LOCATION_CLARIFICATION
                session.active_clarification_question = loc_res.clarification_question.model_dump()
                return IVRTurnResult(
                    prompt_text=loc_res.clarification_question.prompt_text,
                    next_state=IVRCallState.AWAITING_LOCATION_CLARIFICATION,
                    expect_input="audio",
                    is_completed=False,
                    extraction=extraction,
                )
            else:
                if session.location_unresolvable_attempts < session.max_state_retries:
                    session.location_unresolvable_attempts += 1
                    unmatched_text = session.location_text
                    session.location_text = None
                    session.current_state = IVRCallState.AWAITING_LOCATION
                    reprompt = (
                        f"Hamein '{unmatched_text}' map par nahi mila. Kripya paas ka hospital, "
                        "railway station, ya main sadak ka naam batayein."
                    )
                    return IVRTurnResult(
                        prompt_text=reprompt,
                        next_state=IVRCallState.AWAITING_LOCATION,
                        expect_input="audio",
                        is_completed=False,
                        extraction=extraction,
                    )
                else:
                    session.location_resolved = True
        elif self.location_resolver is None and session.location_text:
            session.location_resolved = True

        # Handle headcount & readback logic
        extracted_headcount = extraction.people_count
        if (
            (session.current_state == IVRCallState.AWAITING_PEOPLE_COUNT or session.people_count is None)
            and extracted_headcount is not None
            and not extraction.is_completed
            and not session.needs
        ):
            # Preserves readback confirmation safety gate for spoken headcount
            session.people_count_unconfirmed = extracted_headcount
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT_READBACK
            readback_prompt = generate_number_readback_prompt(extracted_headcount, session.language_code)
            return IVRTurnResult(
                prompt_text=readback_prompt,
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT_READBACK,
                expect_input="any",
                is_completed=False,
                extraction=extraction,
            )
        elif extracted_headcount is not None:
            session.people_count = extracted_headcount
            session.people_count_confirmed = True

        # 5. Determine Completion & Adaptive Next Question
        has_all_facts = bool(session.location_text and session.people_count and session.needs)
        is_completed = extraction.is_completed or has_all_facts or (session.current_state == IVRCallState.AWAITING_NEEDS)

        # Critical P0 Safety Probing:
        # If water hazard is detected and the probe has not been answered yet,
        # ask the critical safety probe question BEFORE completing the call!
        if is_completed and session.water_hazard_detected and not session.safety_probe_answered:
            session.current_state = IVRCallState.AWAITING_SAFETY_PROBE
            return IVRTurnResult(
                prompt_text="Paani kitna gehra hai aur kya koi bimar, vriddh, ya garbhwati mahila hain?",
                next_state=IVRCallState.AWAITING_SAFETY_PROBE,
                expect_input="audio",
                is_completed=False,
                extraction=extraction,
            )

        if is_completed:
            session.current_state = IVRCallState.COMPLETED
            submission = session.to_submission()
            if self.ingestion_service:
                self.ingestion_service.ingest(submission)
            prompt = extraction.next_prompt or "Aapka sandesh darj kar liya gaya hai. Bachav dal ko suchit kiya ja raha hai."
            return IVRTurnResult(
                prompt_text=prompt,
                next_state=IVRCallState.COMPLETED,
                expect_input="none",
                is_completed=True,
                submission=submission,
                extraction=extraction,
            )

        # Missing headcount
        if session.location_text and session.people_count is None:
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            prompt = extraction.next_prompt or f"{session.location_text} note kar liya hai. Aapke saath kitne log hain? Sankhya batayein ya keypad dabayein."
            return IVRTurnResult(
                prompt_text=prompt,
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="any",
                is_completed=False,
                extraction=extraction,
            )

        # Missing needs/hazards
        if session.location_text and session.people_count is not None and not session.needs:
            session.current_state = IVRCallState.AWAITING_NEEDS
            prompt = extraction.next_prompt or f"{session.people_count} log darj hue. Kis tarah ki madad chahiye? Jaise ki naav, doctor, ya bhojan?"
            return IVRTurnResult(
                prompt_text=prompt,
                next_state=IVRCallState.AWAITING_NEEDS,
                expect_input="audio",
                is_completed=False,
                extraction=extraction,
            )

        # Missing location
        session.current_state = IVRCallState.AWAITING_LOCATION
        prompt = extraction.next_prompt or "Aap kahan phanse hain? Kripya apna sthan ya aas paas ka landmark batayein."
        return IVRTurnResult(
            prompt_text=prompt,
            next_state=IVRCallState.AWAITING_LOCATION,
            expect_input="audio",
            is_completed=False,
            extraction=extraction,
        )

    # ------------------------------------------------------------------
    # DTMF Keypad & Readback Fallbacks
    # ------------------------------------------------------------------

    async def _handle_dtmf_input(
        self,
        session: IVRCallSession,
        dtmf_digits: str,
    ) -> IVRTurnResult:
        state = session.current_state

        if state == IVRCallState.AWAITING_LOCATION:
            session.location_code_dtmf = dtmf_digits.strip()
            session.state_retries = 0
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            return IVRTurnResult(
                prompt_text="Ward code darj ho gaya. Aapke saath kitne log hain? Sankhya batayein ya keypad par dabayein.",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="any",
                is_completed=False,
            )

        if state == IVRCallState.AWAITING_PEOPLE_COUNT:
            if dtmf_digits.strip().isdigit():
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

        if state == IVRCallState.AWAITING_NEEDS:
            session.situation_description = f"DTMF Input: {dtmf_digits}"
            session.current_state = IVRCallState.COMPLETED
            submission = session.to_submission()
            if self.ingestion_service:
                self.ingestion_service.ingest(submission)
            return IVRTurnResult(
                prompt_text="Aapka sandesh darj kar liya gaya hai. Bachav dal ko suchit kiya ja raha hai.",
                next_state=IVRCallState.COMPLETED,
                expect_input="none",
                is_completed=True,
                submission=submission,
            )

        return IVRTurnResult(
            prompt_text="Kripya aawaz mein batayein.",
            next_state=state,
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

    async def _handle_location_clarification(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        spoken_text = ""
        if audio is not None and self.vad_detector.detect_speech(audio):
            transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
            session.transcripts.append(transcript)
            spoken_text = transcript.text.strip()
        elif dtmf_digits:
            spoken_text = dtmf_digits.strip()

        active_q = session.active_clarification_question or {}
        q_id = active_q.get("question_id", "q1")
        options = active_q.get("options", [])

        if not spoken_text:
            session.state_retries += 1
            if session.state_retries >= session.max_state_retries:
                session.location_resolved = True
                session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
                return IVRTurnResult(
                    prompt_text="Theek hai. Aapke saath kitne log hain? Sankhya batayein.",
                    next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                    expect_input="any",
                    is_completed=False,
                )
            prompt = active_q.get("prompt_text") or "Kripya sahi vikalp batayein."
            return IVRTurnResult(
                prompt_text=prompt,
                next_state=IVRCallState.AWAITING_LOCATION_CLARIFICATION,
                expect_input="audio",
                is_completed=False,
            )

        selected_option = spoken_text
        if spoken_text.isdigit() and options:
            idx = int(spoken_text) - 1
            if 0 <= idx < len(options):
                selected_option = options[idx]

        answer = {
            "question_id": q_id,
            "selected_option": selected_option,
            "text_response": spoken_text,
        }
        session.clarification_answers.append(answer)

        if self.location_resolver is not None:
            obs_answers = [
                ClarificationAnswer(
                    question_id=a["question_id"],
                    selected_option=a.get("selected_option"),
                    text_response=a.get("text_response"),
                )
                for a in session.clarification_answers
            ]
            loc_obs = LocationObservation(
                incident_id=session.disaster_id,
                raw_text=session.location_text,
                answers=obs_answers,
            )
            loc_res = await self.location_resolver.resolve(loc_obs)
            if loc_res.resolved_landmark is not None:
                session.location_text = loc_res.resolved_landmark.name
            session.location_resolved = True
        else:
            session.location_resolved = True

        session.state_retries = 0

        if session.people_count is None:
            session.current_state = IVRCallState.AWAITING_PEOPLE_COUNT
            return IVRTurnResult(
                prompt_text=f"{session.location_text} note kar liya hai. Aapke saath kitne log hain? Sankhya batayein ya keypad dabayein.",
                next_state=IVRCallState.AWAITING_PEOPLE_COUNT,
                expect_input="any",
                is_completed=False,
            )
        elif not session.needs:
            session.current_state = IVRCallState.AWAITING_NEEDS
            return IVRTurnResult(
                prompt_text=f"{session.people_count} log darj hue. Kis tarah ki madad chahiye? Jaise ki naav, doctor, ya bhojan?",
                next_state=IVRCallState.AWAITING_NEEDS,
                expect_input="audio",
                is_completed=False,
            )
        else:
            session.current_state = IVRCallState.COMPLETED
            sub = session.to_submission()
            if self.ingestion_service:
                self.ingestion_service.ingest(sub)
            return IVRTurnResult(
                prompt_text="Aapka sandesh darj kar liya gaya hai. Bachav dal ko suchit kiya ja raha hai.",
                next_state=IVRCallState.COMPLETED,
                expect_input="none",
                is_completed=True,
                submission=sub,
            )

    async def _handle_safety_probe(
        self,
        session: IVRCallSession,
        audio: Optional[AudioInput],
        dtmf_digits: Optional[str],
    ) -> IVRTurnResult:
        spoken_text = ""
        if audio is not None and self.vad_detector.detect_speech(audio):
            transcript = await self.speech_recognizer.transcribe(audio, language_hint=session.language_code)
            session.transcripts.append(transcript)
            spoken_text = transcript.text.strip()
        elif dtmf_digits:
            spoken_text = dtmf_digits.strip()

        session.safety_probe_answered = True
        session.state_retries = 0

        if spoken_text:
            text_lower = spoken_text.lower()
            if any(w in text_lower for w in ["bimar", "sick", "elderly", "vriddh", "bujurg", "pregnant", "garbhwati", "bachha", "child"]):
                if "medical" not in session.needs:
                    session.needs.append("medical")
            if session.situation_description:
                session.situation_description += f" | Safety Probe: {spoken_text}"
            else:
                session.situation_description = f"Safety Probe: {spoken_text}"

        session.current_state = IVRCallState.COMPLETED
        submission = session.to_submission()
        if self.ingestion_service:
            self.ingestion_service.ingest(submission)

        prompt = (
            f"Jankari darj ho gayi hai: {session.location_text or 'Aapke sthan'} par "
            f"{session.people_count or 1} logon ke liye. Aapatkalin bachav dal ko turant "
            "rawana kiya ja raha hai. Kripya oonche sthan par rahein, madad pahunch rahi hai!"
        )
        return IVRTurnResult(
            prompt_text=prompt,
            next_state=IVRCallState.COMPLETED,
            expect_input="none",
            is_completed=True,
            submission=submission,
        )
