"""Public guided voice calls. Mounted only when PUBLIC_INTAKE_ENABLED is set.

A caller opens a call for their district and receives a secret token. Each
answer (a WAV recording or typed text) is sent with that token; the response
carries what was understood and the next question. Prompts are spoken by
Gnani Timbre and fetched separately so they can be cached.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from raahat.api.deps import client_ip, get_db, rate_limiter
from raahat.api.services import providers
from raahat.application.voicecall import dialogue, script
from raahat.application.voicecall import service as calls
from raahat.config import Settings, get_settings
from raahat.infrastructure.providers.base import ProviderError
from raahat.security.jurisdiction import Jurisdiction, UnknownJurisdiction

router = APIRouter(prefix="/public", tags=["public voice call"])

MAX_TURN_AUDIO_BYTES = 3 * 1024 * 1024
PROMPT_KEYS = frozenset({*script.STEPS, "greeting", "done", "retry"})


class PromptLine(BaseModel):
    language: str
    key: str
    text: str


class FactsView(BaseModel):
    people_count: Optional[int]
    trapped: bool
    medical: bool
    place: Optional[str]
    phone: Optional[str]
    name: Optional[str]


class CallState(BaseModel):
    call_id: uuid.UUID
    step: str
    language: str
    language_name: str
    language_source: str
    district: str
    state: str
    prompt: list[PromptLine]
    facts: FactsView
    done: bool
    ticket: Optional[uuid.UUID] = None


class StartedCall(CallState):
    token: str


class TurnResult(CallState):
    heard: str
    via: str
    speech_failed: bool


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_code: str = Field(max_length=8)
    district_code: str = Field(max_length=8)


class PositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(default=None, ge=0, le=100000)


class LanguageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(max_length=8)


def _limit(request: Request, settings: Settings, bucket: str, limit: int) -> None:
    decision = rate_limiter.check(f"{bucket}:{client_ip(request, settings)}", limit=limit)
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please wait a moment.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _lines(language: str, step: str, *, repeat: bool = False, first: bool = False) -> list[PromptLine]:
    if first:
        return [PromptLine(language=o.language, key="greeting", text=o.text) for o in script.opening()]
    key = "retry" if repeat else step
    line = script.line(language, key)
    return [PromptLine(language=line.language, key=key, text=line.text)]


def _state(call, *, prompt: list[PromptLine]) -> dict:
    facts = dialogue.Facts.load(call.slots)
    j = Jurisdiction(call.state_code, call.district_code)
    return dict(
        call_id=call.id, step=call.step, language=call.language,
        language_name=script.LANGUAGE_NAMES[call.language], language_source=call.language_source,
        district=j.district_name or "", state=j.state_name or "", prompt=prompt,
        facts=FactsView(
            people_count=facts.people_count, trapped=facts.trapped, medical=facts.medical,
            place=facts.place, phone=facts.phone, name=facts.name,
        ),
        done=call.status == "submitted", ticket=call.report_id,
    )


def _call(session: Session, call_id: uuid.UUID, token: Optional[str], *, lock: bool = True):
    try:
        return calls.load(session, call_id, token or "", for_update=lock)
    except calls.CallNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


def _fail(exc: calls.CallError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/calls", response_model=StartedCall, status_code=status.HTTP_201_CREATED,
             summary="Start a guided voice call for a district")
def start_call(
    body: StartRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StartedCall:
    _limit(request, settings, "call-start", settings.public_rate_per_minute)
    try:
        jurisdiction = Jurisdiction.validated(body.state_code, body.district_code)
        if jurisdiction.district_code is None:
            raise UnknownJurisdiction("Choose your district")
    except UnknownJurisdiction as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    call, token = calls.start(session, jurisdiction=jurisdiction, client_ip=client_ip(request, settings))
    return StartedCall(token=token, **_state(call, prompt=_lines(call.language, call.step, first=True)))


@router.post("/calls/{call_id}/turns", response_model=TurnResult, summary="Answer the current question")
def answer(
    call_id: uuid.UUID,
    request: Request,
    step: str = Form(..., max_length=32),
    text: Optional[str] = Form(None, max_length=2000),
    audio: Optional[UploadFile] = File(None),
    x_call_token: Optional[str] = Header(None),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TurnResult:
    _limit(request, settings, "call", settings.voice_call_rate_per_minute)
    data: Optional[bytes] = None
    if audio is not None:
        data = audio.file.read(MAX_TURN_AUDIO_BYTES + 1)
        if len(data) > MAX_TURN_AUDIO_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That answer is too long. Keep it under a minute.")
    call = _call(session, call_id, x_call_token)
    try:
        turn = calls.take_turn(
            session, call, step=step, audio=data or None, typed=text,
            speech=providers().speech, audio_dir=settings.audio_storage_dir,
        )
        ticket = None
        if turn.outcome.step == dialogue.DONE:
            ticket = calls.submit(session, call, audio_dir=settings.audio_storage_dir, reason="completed")
    except calls.CallError as exc:
        raise _fail(exc) from None
    if turn.outcome.step == dialogue.DONE:
        prompt = _lines(call.language, "done")
    else:
        prompt = _lines(call.language, turn.outcome.step, repeat=turn.outcome.repeat)
    state = _state(call, prompt=prompt)
    state["ticket"] = ticket or state["ticket"]
    return TurnResult(heard=turn.transcript, via=turn.via, speech_failed=turn.speech_failed, **state)


@router.post("/calls/{call_id}/language", response_model=CallState, summary="Choose the call language")
def set_language(
    call_id: uuid.UUID,
    body: LanguageRequest,
    request: Request,
    x_call_token: Optional[str] = Header(None),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CallState:
    _limit(request, settings, "call", settings.voice_call_rate_per_minute)
    if body.language != "auto" and body.language not in script.SUPPORTED:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That language is not supported")
    call = _call(session, call_id, x_call_token)
    try:
        calls.choose_language(session, call, body.language)
    except calls.CallError as exc:
        raise _fail(exc) from None
    return CallState(**_state(call, prompt=_lines(call.language, call.step)))


@router.put("/calls/{call_id}/position", response_model=CallState, summary="Attach the device position")
def set_position(
    call_id: uuid.UUID,
    body: PositionRequest,
    request: Request,
    x_call_token: Optional[str] = Header(None),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CallState:
    _limit(request, settings, "call", settings.voice_call_rate_per_minute)
    call = _call(session, call_id, x_call_token)
    try:
        calls.set_position(
            session, call, latitude=body.latitude, longitude=body.longitude, accuracy_m=body.accuracy_m
        )
    except calls.CallError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from None
    return CallState(**_state(call, prompt=[]))


@router.post("/calls/{call_id}/finish", response_model=CallState, summary="Send the report now")
def finish(
    call_id: uuid.UUID,
    request: Request,
    reason: Literal["caller_sent", "caller_left"] = Query("caller_sent"),
    x_call_token: Optional[str] = Header(None),
    token: Optional[str] = Query(None, max_length=128),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CallState:
    """Send whatever has been said so far. Also called when the caller leaves the page.

    ``token`` may be given as a query parameter for browsers' leave-page
    beacon, which cannot set headers.
    """
    _limit(request, settings, "call", settings.voice_call_rate_per_minute)
    call = _call(session, call_id, x_call_token or token)
    ticket = calls.submit(session, call, audio_dir=settings.audio_storage_dir, reason=reason)
    prompt = _lines(call.language, "done") if ticket else []
    state = _state(call, prompt=prompt)
    return CallState(**state)


@router.get("/voice/{language}/{key}.wav", summary="A spoken prompt", response_class=Response)
def prompt_audio(
    language: str,
    key: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    _limit(request, settings, "call-audio", settings.voice_call_rate_per_minute)
    if language not in script.SUPPORTED or key not in PROMPT_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such prompt")
    if key == "greeting" and language not in ("hi", "en"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such prompt")
    voice = providers().voice
    if voice is None or not voice.configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Spoken prompts are not available")
    line = script.line(language, key)
    try:
        audio = voice.synthesize(line.spoken, language=line.language)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The voice service did not respond") from exc
    return Response(
        audio, media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=86400"},
    )
