"""Guided voice calls from the public reporting site.

A call belongs to the district the caller chose. Each answer is transcribed
by Gnani Prisma with automatic language identification; the agent then
speaks in that language (Hindi when the language is not recognised). When
the interview ends, or the caller sends early, or leaves the page, the call
becomes one report in that district's operation, with every answer in the
caller's own words and the recordings joined into one file.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import logging
import secrets
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from raahat.application.intake import service as intake
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.voice_call import VoiceCallModel
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.infrastructure.providers.base import ProviderError
from raahat.infrastructure.providers.gnani_prisma import GnaniPrismaClient
from raahat.security.jurisdiction import Jurisdiction

from . import dialogue, script

logger = logging.getLogger(__name__)

CALL_TTL = timedelta(minutes=30)
ABANDONED_AFTER = timedelta(minutes=3)
MAX_TURNS = 24
SAMPLE_RATE = 16000


class CallError(Exception):
    """A problem the caller can be told about."""


class CallNotFound(CallError):
    pass


@dataclass(frozen=True)
class Turn:
    transcript: str
    via: str
    language: str
    language_source: str
    outcome: dialogue.Outcome
    facts: dialogue.Facts
    speech_failed: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --------------------------------------------------------------------- routing
def operation_for(session: Session, jurisdiction: Jurisdiction) -> DisasterModel:
    """The operation that receives public reports for a district.

    The newest active operation for the district; otherwise the newest active
    state-wide one; otherwise the district's standing operation, created on
    first use. Does not commit.
    """
    assert jurisdiction.state_code and jurisdiction.district_code
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
        {"k": f"standing-operation:{jurisdiction.district_code}"},
    )
    base = select(DisasterModel).where(
        DisasterModel.status == "active", DisasterModel.state_code == jurisdiction.state_code
    )
    found = session.execute(
        base.where(DisasterModel.district_code == jurisdiction.district_code)
        .order_by(DisasterModel.is_standing.asc(), DisasterModel.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if found is None:
        found = session.execute(
            base.where(DisasterModel.district_code.is_(None))
            .order_by(DisasterModel.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    if found is not None:
        return found
    operation = DisasterModel(
        id=uuid.uuid4(),
        name=f"{jurisdiction.district_name}: public emergency reports",
        disaster_type="other",
        status="active",
        description="Receives reports made by the public through the reporting site "
        "while no named operation is active in this district.",
        area_name=f"{jurisdiction.district_name}, {jurisdiction.state_name}",
        state_code=jurisdiction.state_code,
        district_code=jurisdiction.district_code,
        is_standing=True,
        started_at=_now(),
    )
    session.add(operation)
    session.flush()
    append_audit(
        session, action="operation.opened", actor_id=None, entity_type="disaster",
        entity_id=operation.id, disaster_id=operation.id,
        payload={"name": operation.name, "type": "other", "standing": True,
                 "state_code": jurisdiction.state_code, "district_code": jurisdiction.district_code},
    )
    return operation


# ------------------------------------------------------------------- lifecycle
def start(session: Session, *, jurisdiction: Jurisdiction, client_ip: Optional[str]) -> tuple[VoiceCallModel, str]:
    """Open a call for a district. Returns the call and its secret token. Commits."""
    if jurisdiction.district_code is None:
        raise CallError("Choose your district")
    token = secrets.token_urlsafe(32)
    call = VoiceCallModel(
        id=uuid.uuid4(),
        token_hash=_hash(token),
        state_code=jurisdiction.state_code,
        district_code=jurisdiction.district_code,
        language=script.DEFAULT_LANGUAGE,
        language_source="default",
        status="open",
        step="situation",
        slots=dialogue.Facts().dump(),
        turns=[],
        client_ip=(client_ip or "")[:64] or None,
    )
    session.add(call)
    session.commit()
    return call, token


def load(session: Session, call_id: uuid.UUID, token: str, *, for_update: bool = False) -> VoiceCallModel:
    stmt = select(VoiceCallModel).where(VoiceCallModel.id == call_id)
    if for_update:
        stmt = stmt.with_for_update()
    call = session.execute(stmt).scalar_one_or_none()
    if call is None or not hmac.compare_digest(call.token_hash, _hash(token or "")):
        raise CallNotFound("This call has ended. Start a new one.")
    return call


def _open(call: VoiceCallModel) -> None:
    if call.status != "open":
        raise CallError("This call has already been sent.")
    if _now() - call.created_at > CALL_TTL:
        raise CallError("This call has timed out. Start a new one.")
    if len(call.turns) >= MAX_TURNS:
        raise CallError("This call is too long. Send it now.")


def choose_language(session: Session, call: VoiceCallModel, language: str) -> None:
    _open(call)
    if language == "auto":
        call.language_source = "default" if not call.turns else call.language_source
    else:
        call.language = script.supported(language)
        call.language_source = "chosen"
    session.commit()


def set_position(
    session: Session, call: VoiceCallModel, *, latitude: float, longitude: float, accuracy_m: Optional[float]
) -> None:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or (latitude == 0 and longitude == 0):
        raise CallError("That position is not valid")
    if call.status == "submitted":
        raise CallError("This call has already been sent.")
    call.latitude, call.longitude = latitude, longitude
    call.location_accuracy_m = accuracy_m
    session.commit()


def take_turn(
    session: Session,
    call: VoiceCallModel,
    *,
    step: str,
    audio: Optional[bytes],
    typed: Optional[str],
    speech: GnaniPrismaClient,
    audio_dir: Path,
) -> Turn:
    """Record one answer (spoken or typed) and move the interview on. Commits."""
    _open(call)
    if step != call.step:
        raise CallError("That answer was for an earlier question. Please answer the current one.")

    transcript = (typed or "").strip()[:2000]
    via = "text"
    detected: Optional[str] = None
    speech_failed = False
    stored: Optional[str] = None
    confidence: Optional[float] = None
    if not transcript and audio:
        via = "voice"
        stored = intake.save_audio(audio_dir, data=audio, filename="turn.wav")["stored_name"]
        hint = call.language if call.language_source == "chosen" else None
        try:
            result = speech.transcribe(audio, language_hint=hint)
            transcript, detected, confidence = result.text.strip(), result.language, result.confidence
        except ProviderError as exc:
            logger.warning("Voice call %s: transcription failed: %s", call.id, exc)
            speech_failed = True
    elif transcript:
        detected = script.language_of_text(transcript)

    if transcript and call.language_source == "default":
        call.language = script.supported(detected)
        call.language_source = "detected" if via == "voice" else "script"

    facts = dialogue.Facts.load(call.slots)
    outcome = dialogue.answer(facts, step, transcript)
    call.slots = facts.dump()
    call.turns = [
        *call.turns,
        {
            "step": step,
            "question": script.line(call.language, step).text,
            "answer": transcript,
            "via": via,
            "detected_language": detected,
            "confidence": confidence,
            "audio": stored,
            "speech_failed": speech_failed,
            "at": _now().isoformat(),
        },
    ]
    call.step = outcome.step
    session.commit()
    return Turn(transcript, via, call.language, call.language_source, outcome, facts, speech_failed)


def _joined_audio(call: VoiceCallModel, audio_dir: Path) -> Optional[bytes]:
    """All spoken answers as one 16 kHz mono WAV, in order. Skips unreadable parts."""
    frames: list[bytes] = []
    for turn in call.turns:
        name = turn.get("audio")
        if not name:
            continue
        try:
            with wave.open(str(audio_dir / name), "rb") as part:
                if part.getnchannels() != 1 or part.getsampwidth() != 2 or part.getframerate() != SAMPLE_RATE:
                    continue
                frames.append(part.readframes(part.getnframes()))
        except (OSError, wave.Error, EOFError):
            continue
    if not frames:
        return None
    gap = b"\x00\x00" * (SAMPLE_RATE // 2)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(gap.join(frames))
    return buffer.getvalue()


def submit(session: Session, call: VoiceCallModel, *, audio_dir: Path, reason: str) -> Optional[uuid.UUID]:
    """Turn the call into a report. Returns the ticket, or None if nothing was said. Commits."""
    if call.status == "submitted":
        return call.report_id
    facts = dialogue.Facts.load(call.slots)
    narrative = dialogue.narrative(facts)
    if not narrative and call.latitude is None:
        call.status = "abandoned"
        session.commit()
        return None

    jurisdiction = Jurisdiction(call.state_code, call.district_code)
    operation = operation_for(session, jurisdiction)
    payload: dict[str, Any] = {
        "situation_description": narrative or None,
        "location_text": facts.place,
        "people_count": facts.people_count,
        "phone_number": facts.phone,
        "caller_name": facts.name,
        "latitude": call.latitude,
        "longitude": call.longitude,
        "location_accuracy_m": call.location_accuracy_m,
        "state": jurisdiction.state_name,
        "district": jurisdiction.district_name,
        "voice_call": {
            "call_id": str(call.id),
            "language": call.language,
            "language_source": call.language_source,
            "ended": reason,
            "transcript": [
                {k: t.get(k) for k in ("step", "question", "answer", "via", "detected_language", "at")}
                for t in call.turns
            ],
        },
    }
    joined = _joined_audio(call, audio_dir)
    if joined is not None:
        payload["audio"] = {
            **intake.save_audio(audio_dir, data=joined, filename="call.wav"),
            "content_type": "audio/wav",
        }
    submission = ReportSubmission(
        disaster_id=operation.id,
        source_type=SourceType.WEB,
        source_identity=facts.phone,
        channel_reference="web_voice_call",
        raw_payload={k: v for k, v in payload.items() if v is not None},
        language_code=call.language,
        idempotency_key=f"voice-call-{call.id}",
    )
    session.commit()  # the standing operation, if one was created
    report, _ = intake.store_channel_report(session, submission)
    call.report_id = report.id
    call.status = "submitted"
    call.submitted_at = _now()
    session.commit()
    return report.id


def submit_abandoned(session: Session, *, audio_dir: Path, now: Optional[datetime] = None) -> int:
    """Send calls the caller left mid-interview. Returns how many became reports."""
    cutoff = (now or _now()) - ABANDONED_AFTER
    ids = session.execute(
        select(VoiceCallModel.id)
        .where(VoiceCallModel.status == "open", VoiceCallModel.updated_at < cutoff)
        .limit(20)
    ).scalars().all()
    sent = 0
    for call_id in ids:
        call = session.execute(
            select(VoiceCallModel).where(VoiceCallModel.id == call_id).with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if call is None or call.status != "open":
            session.rollback()
            continue
        if submit(session, call, audio_dir=audio_dir, reason="caller_left") is not None:
            sent += 1
    return sent
