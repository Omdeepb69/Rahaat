"""Public citizen intake. Mounted only when PUBLIC_INTAKE_ENABLED is set.

These are the only unauthenticated endpoints that write data. Each is rate
limited per client address and size limited, and nothing they return exposes
another person's report.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from raahat.adapters.channels import WebSOSAdapter, WebSOSPayload
from raahat.api.deps import client_ip, get_db, rate_limiter
from raahat.application.intake import service as intake
from raahat.config import Settings, get_settings
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models.disaster import DisasterModel
from raahat.infrastructure.database.models.report import ReportModel

router = APIRouter(prefix="/public", tags=["public intake"])


class PublicAccepted(BaseModel):
    ticket: uuid.UUID
    received_at: datetime


class PublicOperation(BaseModel):
    id: uuid.UUID
    name: str


class TicketStatus(BaseModel):
    ticket: uuid.UUID
    received_at: datetime
    stage: str
    message: str


def _limit(request: Request, settings: Settings) -> None:
    decision = rate_limiter.check(
        f"public:{client_ip(request, settings)}", limit=settings.public_rate_per_minute
    )
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please wait and try again.",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


@router.get("/operations", response_model=list[PublicOperation], summary="Operations accepting reports")
def public_operations(
    request: Request, session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> list[PublicOperation]:
    _limit(request, settings)
    rows = session.execute(
        select(DisasterModel.id, DisasterModel.name)
        .where(DisasterModel.status == "active")
        .order_by(DisasterModel.created_at.desc())
        .limit(20)
    ).all()
    return [PublicOperation(id=r.id, name=r.name) for r in rows]


def _store(session: Session, submission: ReportSubmission) -> PublicAccepted:
    try:
        report, _ = intake.store_channel_report(session, submission)
    except (LookupError, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active operation with that id") from None
    return PublicAccepted(ticket=report.id, received_at=report.received_at)


@router.post("/reports", response_model=PublicAccepted, status_code=status.HTTP_202_ACCEPTED,
             summary="Submit an emergency report")
def public_report(
    payload: WebSOSPayload,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PublicAccepted:
    _limit(request, settings)
    return _store(session, WebSOSAdapter.to_submission(payload))


@router.post("/reports/voice", response_model=PublicAccepted, status_code=status.HTTP_202_ACCEPTED,
             summary="Submit an emergency report with a voice recording")
async def public_voice_report(
    request: Request,
    audio: UploadFile = File(...),
    disaster_id: uuid.UUID = Form(...),
    caller_name: Optional[str] = Form(None, max_length=160),
    phone_number: Optional[str] = Form(None, max_length=64),
    location_text: Optional[str] = Form(None, max_length=512),
    latitude: Optional[float] = Form(None, ge=-90, le=90),
    longitude: Optional[float] = Form(None, ge=-180, le=180),
    people_count: Optional[int] = Form(None, ge=1, le=100000),
    language_code: Optional[str] = Form(None, max_length=16),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PublicAccepted:
    _limit(request, settings)
    data = await audio.read(settings.max_audio_upload_bytes + 1)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The recording is empty")
    if len(data) > settings.max_audio_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "The recording is too large")
    stored = intake.save_audio(settings.audio_storage_dir, data=data, filename=audio.filename)
    submission = ReportSubmission(
        disaster_id=disaster_id,
        source_type=SourceType.WEB,
        source_identity=phone_number,
        channel_reference="web_voice",
        raw_payload={
            "caller_name": caller_name,
            "phone_number": phone_number,
            "location_text": location_text,
            "latitude": latitude,
            "longitude": longitude,
            "people_count": people_count,
            "audio": {**stored, "content_type": audio.content_type},
        },
        language_code=language_code,
        idempotency_key=f"web-voice-{stored['stored_name']}",
    )
    return _store(session, submission)


@router.get("/tickets/{ticket}", response_model=TicketStatus, summary="Check the status of a submitted report")
def ticket_status(
    ticket: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TicketStatus:
    """Coarse status only. Nothing about the report's content or responders is returned."""
    _limit(request, settings)
    report = session.get(ReportModel, ticket)
    if report is None or report.source_type != SourceType.WEB.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    row = session.execute(
        text(
            "SELECT i.status, EXISTS (SELECT 1 FROM assignments a WHERE a.incident_id = i.id "
            "AND a.status IN ('approved','completed')) AS responding "
            "FROM incident_reports ir JOIN incidents i ON i.id = ir.incident_id "
            "WHERE ir.report_id = :id ORDER BY ir.created_at LIMIT 1"
        ),
        {"id": ticket},
    ).first()
    if row is None:
        stage, message = "received", "Your report has been received and is waiting to be reviewed."
    elif row.status in ("resolved", "closed"):
        stage, message = "closed", "The control room has closed this report."
    elif row.responding:
        stage, message = "responding", "The control room has assigned responders to this report."
    elif row.status in ("verified", "assigned", "in_progress"):
        stage, message = "confirmed", "The control room has confirmed your report."
    else:
        stage, message = "under_review", "The control room is reviewing your report."
    return TicketStatus(ticket=ticket, received_at=report.received_at, stage=stage, message=message)
