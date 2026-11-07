"""Report ingestion and query REST endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from raahat.adapters.channels.radio_console import RadioConsoleAdapter, RadioConsolePayload
from raahat.adapters.channels.sms import SMSAdapter, SMSPayload
from raahat.adapters.channels.web import WebSOSAdapter, WebSOSPayload
from raahat.api.dependencies import get_db, get_ingestion_service, get_session_factory
from raahat.application.ingestion import (
    DisasterNotFoundError,
    IngestionResult,
    ReportIngestionService,
)
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType
from raahat.infrastructure.database.models.report import ReportModel

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GenericReportSubmissionRequest(BaseModel):
    """Payload for submitting a report directly from an integrated channel."""

    model_config = ConfigDict(extra="forbid")

    disaster_id: uuid.UUID
    source_type: SourceType
    source_event_id: Optional[str] = None
    source_identity: Optional[str] = None
    device_id: Optional[uuid.UUID] = None
    channel_reference: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    client_created_at: Optional[datetime] = None
    language_code: Optional[str] = None
    idempotency_key: Optional[str] = None


class IngestionResponse(BaseModel):
    """Standardized response after report ingestion."""

    report_id: uuid.UUID
    disaster_id: uuid.UUID
    status: str
    is_duplicate: bool
    idempotency_key: str
    received_at: datetime


class ReportDetailResponse(BaseModel):
    """Detailed representation of a stored report."""

    id: uuid.UUID
    disaster_id: uuid.UUID
    source_type: str
    source_event_id: Optional[str]
    source_identity: Optional[str]
    device_id: Optional[uuid.UUID]
    channel_reference: Optional[str]
    raw_payload: dict[str, Any]
    received_at: datetime
    client_created_at: Optional[datetime]
    language_code: Optional[str]
    processing_status: str
    idempotency_key: str


class ReportListResponse(BaseModel):
    """Paginated list of reports."""

    items: list[ReportDetailResponse]
    total: int
    limit: int
    offset: int


class TicketStatusResponse(BaseModel):
    """Citizen tracking status for an emergency report ticket."""

    report_id: uuid.UUID
    disaster_id: uuid.UUID
    received_at: datetime
    stage: str
    processing_status: str
    incident_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    assigned_resources: list[str] = Field(default_factory=list)
    message: str


def _result_to_response(result: IngestionResult) -> JSONResponse:
    content = IngestionResponse(
        report_id=result.report_id,
        disaster_id=result.disaster_id,
        status=result.status,
        is_duplicate=result.is_duplicate,
        idempotency_key=result.idempotency_key,
        received_at=result.received_at,
    ).model_dump(mode="json")

    status_code = status.HTTP_200_OK if result.is_duplicate else status.HTTP_201_CREATED
    return JSONResponse(status_code=status_code, content=content)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a distress report",
)
def submit_report(
    req: GenericReportSubmissionRequest,
    service: ReportIngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    submission = ReportSubmission(
        disaster_id=req.disaster_id,
        source_type=req.source_type,
        source_event_id=req.source_event_id,
        source_identity=req.source_identity,
        device_id=req.device_id,
        channel_reference=req.channel_reference,
        raw_payload=req.raw_payload,
        client_created_at=req.client_created_at,
        language_code=req.language_code,
        idempotency_key=req.idempotency_key,
    )
    try:
        result = service.ingest(submission)
    except DisasterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return _result_to_response(result)


@router.post(
    "/channels/web",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit report via Web SOS portal",
)
def submit_web_report(
    payload: WebSOSPayload,
    service: ReportIngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    submission = WebSOSAdapter.to_submission(payload)
    try:
        result = service.ingest(submission)
    except DisasterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return _result_to_response(result)


@router.post(
    "/channels/web/voice",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit report with voice recording via Citizen Web SOS portal",
)
async def submit_web_voice_report(
    audio: UploadFile = File(..., description="Audio recording (webm, wav, ogg, mp3)"),
    disaster_id: Optional[uuid.UUID] = Form(None),
    caller_name: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    location_text: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    people_count: Optional[int] = Form(None),
    situation_description: Optional[str] = Form(""),
    needs: Optional[str] = Form(None),
    language_code: Optional[str] = Form("hi"),
    session_factory=Depends(get_session_factory),
    service: ReportIngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    target_disaster_id = disaster_id
    if target_disaster_id is None:
        with session_factory() as session:
            from raahat.infrastructure.database.models.disaster import DisasterModel

            latest = session.scalars(
                select(DisasterModel).order_by(DisasterModel.created_at.desc()).limit(1)
            ).first()
            if latest:
                target_disaster_id = latest.id

    if target_disaster_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active disaster found to associate report with",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty",
        )

    storage_dir = Path("storage/audio")
    storage_dir.mkdir(parents=True, exist_ok=True)
    audio_ext = Path(audio.filename or "recording.webm").suffix or ".webm"
    audio_filename = f"web_voice_{uuid.uuid4().hex[:12]}{audio_ext}"
    audio_path = storage_dir / audio_filename
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    needs_list: list[str] = []
    if needs:
        if needs.startswith("[") and needs.endswith("]"):
            try:
                parsed = json.loads(needs)
                if isinstance(parsed, list):
                    needs_list = [str(x) for x in parsed]
            except Exception:
                needs_list = [n.strip() for n in needs.split(",") if n.strip()]
        else:
            needs_list = [n.strip() for n in needs.split(",") if n.strip()]

    raw_payload: dict[str, Any] = {
        "caller_name": caller_name,
        "phone_number": phone_number,
        "location_text": location_text,
        "latitude": latitude,
        "longitude": longitude,
        "people_count": people_count,
        "situation_description": situation_description or "Voice SOS report submitted via citizen portal",
        "needs": needs_list,
        "audio": {
            "path": str(audio_path),
            "filename": audio.filename or audio_filename,
            "content_type": audio.content_type or "audio/webm",
            "size_bytes": len(audio_bytes),
        },
    }

    submission = ReportSubmission(
        disaster_id=target_disaster_id,
        source_type=SourceType.WEB,
        source_identity=phone_number,
        raw_payload=raw_payload,
        language_code=language_code or "hi",
        idempotency_key=f"web-voice-{uuid.uuid4()}",
    )

    try:
        result = service.ingest(submission)
    except DisasterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return _result_to_response(result)


@router.post(
    "/channels/sms",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit report via SMS gateway",
)
def submit_sms_report(
    payload: SMSPayload,
    service: ReportIngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    submission = SMSAdapter.to_submission(payload)
    try:
        result = service.ingest(submission)
    except DisasterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return _result_to_response(result)


@router.post(
    "/channels/radio",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit report via Radio operator console",
)
def submit_radio_report(
    payload: RadioConsolePayload,
    service: ReportIngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    submission = RadioConsoleAdapter.to_submission(payload)
    try:
        result = service.ingest(submission)
    except DisasterNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    return _result_to_response(result)


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
    summary="Get report by ID",
)
def get_report(
    report_id: uuid.UUID,
    session: Session = Depends(get_db),
) -> ReportDetailResponse:
    report = session.get(ReportModel, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID '{report_id}' not found.",
        )
    return ReportDetailResponse(
        id=report.id,
        disaster_id=report.disaster_id,
        source_type=report.source_type,
        source_event_id=report.source_event_id,
        source_identity=report.source_identity,
        device_id=report.device_id,
        channel_reference=report.channel_reference,
        raw_payload=report.raw_payload,
        received_at=report.received_at,
        client_created_at=report.client_created_at,
        language_code=report.language_code,
        processing_status=report.processing_status,
        idempotency_key=report.idempotency_key,
    )


@router.get(
    "/{report_id}/ticket",
    response_model=TicketStatusResponse,
    summary="Get citizen tracking status for an emergency report ticket",
)
def get_report_ticket_status(
    report_id: uuid.UUID,
    session: Session = Depends(get_db),
) -> TicketStatusResponse:
    report = session.get(ReportModel, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report ticket '{report_id}' not found",
        )

    from raahat.infrastructure.database.models.incident import IncidentModel, IncidentReportModel
    from raahat.infrastructure.database.models.operation import AssignmentModel

    link_stmt = select(IncidentReportModel).where(IncidentReportModel.report_id == report_id)
    link = session.scalars(link_stmt).first()

    incident_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    assigned_resources: list[str] = []
    stage = "received"
    message = "Emergency distress report received and logged in system."

    if report.processing_status in ("processed", "extracted"):
        stage = "processing"
        message = "Report details and audio processed by triage pipeline."

    if link:
        incident = session.get(IncidentModel, link.incident_id)
        if incident:
            incident_id = incident.id
            priority = incident.operational_priority
            stage = "triaged"
            message = f"Report triaged into Incident {str(incident.id)[:8]} with priority '{priority.upper()}'."

            assign_stmt = select(AssignmentModel).where(AssignmentModel.incident_id == incident.id)
            assignments = session.scalars(assign_stmt).all()
            for a in assignments:
                res_name = a.resource.name if a.resource else f"Unit {str(a.resource_id)[:6]}"
                assigned_resources.append(f"{res_name} ({a.status})")
                if a.status in ("approved", "acknowledged", "en_route", "on_scene"):
                    stage = "dispatched"
                    message = f"Rescue unit '{res_name}' dispatched and en route to your location."
                elif a.status in ("rescued", "closed"):
                    stage = "resolved"
                    message = f"Rescue operation completed by '{res_name}'."

    return TicketStatusResponse(
        report_id=report.id,
        disaster_id=report.disaster_id,
        received_at=report.received_at,
        stage=stage,
        processing_status=report.processing_status,
        incident_id=incident_id,
        priority=priority,
        assigned_resources=assigned_resources,
        message=message,
    )


@router.get(
    "",
    response_model=ReportListResponse,
    summary="List reports with optional filters",
)
def list_reports(
    disaster_id: Optional[uuid.UUID] = Query(default=None),
    source_type: Optional[str] = Query(default=None),
    processing_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> ReportListResponse:
    stmt = select(ReportModel)
    count_stmt = select(func.count(ReportModel.id))

    if disaster_id is not None:
        stmt = stmt.where(ReportModel.disaster_id == disaster_id)
        count_stmt = count_stmt.where(ReportModel.disaster_id == disaster_id)

    if source_type is not None:
        stmt = stmt.where(ReportModel.source_type == source_type)
        count_stmt = count_stmt.where(ReportModel.source_type == source_type)

    if processing_status is not None:
        stmt = stmt.where(ReportModel.processing_status == processing_status)
        count_stmt = count_stmt.where(ReportModel.processing_status == processing_status)

    total = session.execute(count_stmt).scalar() or 0
    stmt = stmt.order_by(ReportModel.received_at.desc()).limit(limit).offset(offset)
    rows = session.execute(stmt).scalars().all()

    items = [
        ReportDetailResponse(
            id=r.id,
            disaster_id=r.disaster_id,
            source_type=r.source_type,
            source_event_id=r.source_event_id,
            source_identity=r.source_identity,
            device_id=r.device_id,
            channel_reference=r.channel_reference,
            raw_payload=r.raw_payload,
            received_at=r.received_at,
            client_created_at=r.client_created_at,
            language_code=r.language_code,
            processing_status=r.processing_status,
            idempotency_key=r.idempotency_key,
        )
        for r in rows
    ]

    return ReportListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )

