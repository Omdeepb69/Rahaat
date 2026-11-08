"""Interactive Emergency IVR Voice Call routes powered by Gnani Prisma and Timbre."""
from __future__ import annotations

import base64
import logging
import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from raahat.adapters.channels.ivr import IVRCallAgent, IVRCallSession
from raahat.api.dependencies import (
    get_audio_triage_workflow,
    get_ingestion_service,
    get_llm_client,
    get_speech_recognizer,
    get_tts_synthesizer,
)
from raahat.application.ingestion import ReportIngestionService
from raahat.application.workflow import AutomatedAudioTriageWorkflow
from raahat.infrastructure.llm import LLMClient
from raahat.infrastructure.speech import (
    AudioInput,
    SpeechRecognizer,
    SynthesisInput,
    TTSSynthesizer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ivr", tags=["ivr"])

# In-memory store of active interactive IVR sessions
_ACTIVE_SESSIONS: dict[str, IVRCallSession] = {}


class CallStartRequest(BaseModel):
    """Initiate an interactive emergency voice session."""

    disaster_id: uuid.UUID = Field(..., description="Active disaster context identifier")
    caller_phone: str = Field(default="+919820011223", description="Caller phone number")
    language_code: str = Field(default="hi", description="Language code (hi, ml, mr, en, etc.)")


class CallTurnResponse(BaseModel):
    """Result of an interactive emergency dialog turn."""

    call_sid: str
    state: str
    caller_transcript: Optional[str] = None
    detected_language: Optional[str] = None
    prompt_text: str
    prompt_audio_base64: Optional[str] = None
    expect_input: str  # "audio", "dtmf", "any", "none"
    is_completed: bool
    report_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    proposed_resource: Optional[str] = None
    extracted_location: Optional[str] = None
    extracted_people_count: Optional[int] = None
    extracted_needs: list[str] = []
    assessed_priority: Optional[str] = None
    situation_summary: Optional[str] = None


class CallSessionStatusResponse(BaseModel):
    """Inspect current state of an in-flight IVR call."""

    call_sid: str
    disaster_id: uuid.UUID
    caller_phone: str
    state: str
    turn_count: int
    location_text: Optional[str] = None
    people_count: Optional[int] = None
    people_count_confirmed: bool = False
    situation_description: Optional[str] = None
    needs: list[str] = []
    language_code: str = "hi"
    transcripts: list[dict[str, Any]] = []


async def _synthesize_prompt(
    text: str,
    language: str,
    tts: TTSSynthesizer,
) -> Optional[str]:
    """Synthesize text via TTS and return base64-encoded WAV audio."""
    try:
        synth_out = await tts.synthesize(SynthesisInput(text=text, language=language))
        if synth_out.audio_bytes:
            return base64.b64encode(synth_out.audio_bytes).decode("ascii")
    except Exception as exc:
        logger.warning("TTS synthesis failed for prompt '%s': %s", text, exc)
    return None


@router.post(
    "/calls/start",
    response_model=CallTurnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an interactive emergency IVR voice call",
)
async def start_call(
    req: CallStartRequest,
    ingestion: ReportIngestionService = Depends(get_ingestion_service),
    speech_recognizer: SpeechRecognizer = Depends(get_speech_recognizer),
    tts: TTSSynthesizer = Depends(get_tts_synthesizer),
    llm_client: LLMClient = Depends(get_llm_client),
) -> CallTurnResponse:
    """Initialize an emergency voice dialog session.

    Plays initial greeting prompt via Gnani Timbre TTS asking for location and emergency details.
    """
    call_sid = f"CA-{uuid.uuid4().hex[:12].upper()}"
    session = IVRCallSession(
        call_sid=call_sid,
        disaster_id=req.disaster_id,
        caller_phone=req.caller_phone,
        language_code=req.language_code,
    )
    _ACTIVE_SESSIONS[call_sid] = session

    agent = IVRCallAgent(
        speech_recognizer=speech_recognizer,
        ingestion_service=None,
        llm_client=llm_client,
    )

    turn_res = await agent.handle_turn(session)

    audio_b64 = await _synthesize_prompt(turn_res.prompt_text, session.language_code, tts)

    return CallTurnResponse(
        call_sid=call_sid,
        state=turn_res.next_state.value,
        prompt_text=turn_res.prompt_text,
        prompt_audio_base64=audio_b64,
        expect_input=turn_res.expect_input,
        is_completed=turn_res.is_completed,
        extracted_location=session.location_text,
        extracted_people_count=session.people_count,
        extracted_needs=list(session.needs),
        assessed_priority=turn_res.extraction.assessed_priority if turn_res.extraction else "P1",
        situation_summary=session.situation_description,
    )


@router.post(
    "/calls/{call_sid}/turn",
    response_model=CallTurnResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute one conversational turn in an active emergency voice call",
)
async def process_turn(
    call_sid: str,
    audio_file: Optional[UploadFile] = File(None, description="Audio recorded from caller microphone"),
    dtmf_digits: Optional[str] = Form(None, description="DTMF keypad digits entered by caller"),
    text_override: Optional[str] = Form(None, description="Direct text input for testing or fallback"),
    ingestion: ReportIngestionService = Depends(get_ingestion_service),
    speech_recognizer: SpeechRecognizer = Depends(get_speech_recognizer),
    tts: TTSSynthesizer = Depends(get_tts_synthesizer),
    workflow: AutomatedAudioTriageWorkflow = Depends(get_audio_triage_workflow),
    llm_client: LLMClient = Depends(get_llm_client),
) -> CallTurnResponse:
    """Process caller response (voice audio or DTMF) through Gnani Prisma ASR and IVR dialog state machine.

    Synthesizes the system's reply via Gnani Timbre TTS.
    Upon final turn completion, automatically ingests the report and runs downstream
    deterministic triage and nearest-resource proposal.
    """
    session = _ACTIVE_SESSIONS.get(call_sid)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{call_sid}' not found or expired",
        )

    caller_audio: Optional[AudioInput] = None
    caller_transcript_text: Optional[str] = None
    detected_lang: Optional[str] = None

    # Handle voice audio input via Gnani Prisma STT
    if audio_file is not None:
        audio_bytes = await audio_file.read()
        if audio_bytes:
            caller_audio = AudioInput(audio_bytes=audio_bytes, sample_rate=16000)

    # Handle text override (testing / fallback)
    elif text_override and text_override.strip():
        caller_transcript_text = text_override.strip()
        from raahat.infrastructure.speech.mock import MockSpeechRecognizer

        speech_recognizer = MockSpeechRecognizer(
            default_text=caller_transcript_text,
            default_confidence=0.98,
        )
        caller_audio = AudioInput(
            audio_bytes=b"\x00" * 3200 + b"\x7f\x80" * 800,
            sample_rate=16000,
        )

    agent = IVRCallAgent(
        speech_recognizer=speech_recognizer,
        ingestion_service=None,
        llm_client=llm_client,
    )

    turn_res = await agent.handle_turn(
        session=session,
        audio=caller_audio,
        dtmf_digits=dtmf_digits,
    )

    if session.transcripts:
        caller_transcript_text = session.transcripts[-1].text
        detected_lang = session.transcripts[-1].language

    audio_b64 = await _synthesize_prompt(turn_res.prompt_text, session.language_code, tts)

    report_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    proposed_resource: Optional[str] = None

    # When the dialog terminates, trigger automated triage & dispatch recommendation
    if turn_res.is_completed and turn_res.submission is not None:
        try:
            ingest_res = ingestion.ingest(turn_res.submission)
            report_id = ingest_res.report_id

            wf_res = await workflow.run_for_report(report_id=report_id)
            incident_id = wf_res.incident_id
            priority = wf_res.priority.value
            proposed_resource = wf_res.proposed_resource_name
        except Exception as exc:
            logger.error("Downstream triage after IVR completion failed: %s", exc, exc_info=True)

    assessed_p = (
        priority
        or (turn_res.extraction.assessed_priority if turn_res.extraction else "P1")
    )
    summary = session.situation_description or (
        turn_res.extraction.situation_summary if turn_res.extraction else None
    )

    return CallTurnResponse(
        call_sid=call_sid,
        state=turn_res.next_state.value,
        caller_transcript=caller_transcript_text,
        detected_language=detected_lang or session.language_code,
        prompt_text=turn_res.prompt_text,
        prompt_audio_base64=audio_b64,
        expect_input=turn_res.expect_input,
        is_completed=turn_res.is_completed,
        report_id=report_id,
        incident_id=incident_id,
        priority=priority,
        proposed_resource=proposed_resource,
        extracted_location=session.location_text,
        extracted_people_count=session.people_count,
        extracted_needs=list(session.needs),
        assessed_priority=assessed_p,
        situation_summary=summary,
    )


@router.get(
    "/calls/{call_sid}",
    response_model=CallSessionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get status of an active or completed IVR call session",
)
def get_call_session(call_sid: str) -> CallSessionStatusResponse:
    session = _ACTIVE_SESSIONS.get(call_sid)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Call session '{call_sid}' not found",
        )

    return CallSessionStatusResponse(
        call_sid=session.call_sid,
        disaster_id=session.disaster_id,
        caller_phone=session.caller_phone,
        state=session.current_state.value,
        turn_count=session.turn_count,
        location_text=session.location_text,
        people_count=session.people_count,
        people_count_confirmed=session.people_count_confirmed,
        situation_description=session.situation_description,
        needs=session.needs,
        language_code=session.language_code,
        transcripts=[
            {"text": t.text, "confidence": t.confidence, "language": t.language}
            for t in session.transcripts
        ],
    )
