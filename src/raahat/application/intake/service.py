"""Report creation and reading.

Operator-entered reports are analysed in the request so the incident exists by
the time the operator sees the response. Channel reports (web form, voice
note, SMS, radio gateway) are stored and queued for the worker.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from raahat.application.intake.pipeline import (
    AnalysisOutcome,
    ReportPipeline,
    disaster_accepts_reports,
    text_from_payload,
)
from raahat.application.location import service as locations
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import ProcessingStatus, SourceType
from raahat.infrastructure.database.models.incident import IncidentModel
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.models.system import ProcessingRunModel

RECEIVED_VIA = ("phone_call", "walk_in", "radio", "messaging", "field_team", "other")
AUDIO_SUFFIXES = {".webm", ".wav", ".ogg", ".mp3", ".m4a"}


class IntakeError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorReportInput:
    disaster_id: uuid.UUID
    text: str
    received_via: str
    idempotency_key: str
    caller_name: Optional[str] = None
    caller_contact: Optional[str] = None
    location_text: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    people_count: Optional[int] = None
    language_hint: Optional[str] = None


@dataclass(frozen=True)
class CreatedReport:
    report: ReportModel
    outcome: Optional[AnalysisOutcome]
    already_existed: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _find_existing(session: Session, disaster_id: uuid.UUID, key: str) -> Optional[ReportModel]:
    return session.execute(
        select(ReportModel).where(
            ReportModel.disaster_id == disaster_id, ReportModel.idempotency_key == key
        )
    ).scalar_one_or_none()


def create_operator_report(
    session: Session,
    pipeline: ReportPipeline,
    *,
    data: OperatorReportInput,
    actor_id: uuid.UUID,
) -> CreatedReport:
    """Create and analyse a report typed in by an operator. Commits.

    Repeating the call with the same idempotency key returns the report
    created the first time instead of a second one.
    """
    disaster_accepts_reports(session, data.disaster_id)
    if data.received_via not in RECEIVED_VIA:
        raise IntakeError("Unknown intake method")
    body = data.text.strip()
    if not body:
        raise IntakeError("Report text is required")
    has_pin = data.latitude is not None or data.longitude is not None
    if has_pin:
        if data.latitude is None or data.longitude is None:
            raise IntakeError("Latitude and longitude must be given together")
        locations.validate_coordinates(data.latitude, data.longitude)

    key = f"operator:{data.idempotency_key}"
    existing = _find_existing(session, data.disaster_id, key)
    if existing is not None:
        return CreatedReport(existing, None, True)

    payload: dict[str, Any] = {
        "text": body,
        "received_via": data.received_via,
        "caller_name": (data.caller_name or "").strip() or None,
        "phone_number": (data.caller_contact or "").strip() or None,
        "location_text": (data.location_text or "").strip() or None,
        "people_count": data.people_count,
    }
    if has_pin:
        # Kept apart from caller-supplied coordinates: this pin was placed by the operator.
        payload["operator_pin"] = {"latitude": data.latitude, "longitude": data.longitude}

    report = ReportModel(
        id=uuid.uuid4(),
        disaster_id=data.disaster_id,
        source_type=SourceType.OPERATOR.value,
        source_identity=payload["phone_number"],
        channel_reference=data.received_via,
        raw_payload=payload,
        received_at=_now(),
        language_code=(data.language_hint or None),
        processing_status=ProcessingStatus.PENDING.value,
        idempotency_key=key,
        original_text=body,
        original_language=(data.language_hint or None),
        language_source="operator" if data.language_hint else None,
        caller_name=payload["caller_name"],
        caller_contact=payload["phone_number"],
        created_by=actor_id,
    )
    session.add(report)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raced = _find_existing(session, data.disaster_id, key)
        if raced is None:
            raise
        return CreatedReport(raced, None, True)

    outcome = pipeline.analyse(session, report, actor_id=actor_id)
    if has_pin and outcome.incident_id and outcome.is_new_incident:
        locations.set_operator_location(
            session,
            incident_id=outcome.incident_id,
            latitude=float(data.latitude),  # type: ignore[arg-type]
            longitude=float(data.longitude),  # type: ignore[arg-type]
            actor_id=actor_id,
            label="Position entered with the report",
            note="Entered at intake",
        )
    report.processing_status = (
        ProcessingStatus.PENDING_ENRICHMENT.value
        if pipeline.enrichment_available
        else ProcessingStatus.PROCESSED.value
    )
    if report.processing_status == ProcessingStatus.PROCESSED.value:
        report.processed_at = _now()
    session.commit()
    return CreatedReport(report, outcome, False)


def store_channel_report(
    session: Session, submission: ReportSubmission
) -> tuple[ReportModel, bool]:
    """Store a report from an external channel for the worker to analyse. Commits."""
    disaster_accepts_reports(session, submission.disaster_id)
    domain = submission.to_report()
    existing = _find_existing(session, domain.disaster_id, domain.idempotency_key)
    if existing is not None:
        return existing, True
    payload = dict(domain.raw_payload or {})
    name = payload.get("caller_name")
    contact = payload.get("phone_number") or payload.get("phone") or payload.get("sender")
    report = ReportModel(
        id=domain.id,
        disaster_id=domain.disaster_id,
        source_type=domain.source_type.value,
        source_event_id=domain.source_event_id,
        source_identity=domain.source_identity,
        channel_reference=domain.channel_reference,
        raw_payload=payload,
        received_at=domain.received_at,
        client_created_at=domain.client_created_at,
        language_code=domain.language_code,
        processing_status=ProcessingStatus.PENDING.value,
        idempotency_key=domain.idempotency_key,
        original_text=text_from_payload(payload),
        caller_name=str(name)[:160] if name else None,
        caller_contact=str(contact)[:64] if contact else None,
    )
    session.add(report)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raced = _find_existing(session, domain.disaster_id, domain.idempotency_key)
        if raced is None:
            raise
        return raced, True
    return report, False


def save_audio(storage_dir: Path, *, data: bytes, filename: Optional[str]) -> dict[str, Any]:
    """Write an uploaded recording under a generated name. Returns payload metadata."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        suffix = ".webm"
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    (storage_dir / stored_name).write_bytes(data)
    return {"stored_name": stored_name, "size_bytes": len(data)}


def audio_path(storage_dir: Path, report: ReportModel) -> Optional[Path]:
    """Resolve a report's recording, refusing anything outside the storage directory."""
    audio = (report.raw_payload or {}).get("audio")
    if not isinstance(audio, dict):
        return None
    name = audio.get("stored_name") or Path(str(audio.get("path", ""))).name
    if not name or Path(name).name != name:
        return None
    candidate = (storage_dir / name).resolve()
    if storage_dir.resolve() not in candidate.parents or not candidate.is_file():
        return None
    return candidate


_REPORT_LIST = """
    SELECT r.id, r.disaster_id, r.source_type, r.channel_reference, r.received_at,
           r.client_created_at, r.processing_status, r.processing_error, r.processed_at,
           r.original_text, r.original_language, r.language_source, r.translated_text,
           r.translation_provider, r.caller_name, r.caller_contact, r.created_by,
           (r.raw_payload ? 'audio') AS has_audio,
           ir.incident_id, i.reference AS incident_reference, i.status AS incident_status
    FROM reports r
    LEFT JOIN LATERAL (
        SELECT incident_id FROM incident_reports x WHERE x.report_id = r.id
        ORDER BY x.created_at ASC LIMIT 1
    ) ir ON TRUE
    LEFT JOIN incidents i ON i.id = ir.incident_id
"""


def list_reports(
    session: Session,
    *,
    disaster_id: Optional[uuid.UUID] = None,
    channels: Sequence[str] = (),
    statuses: Sequence[str] = (),
    incident_id: Optional[uuid.UUID] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["TRUE"]
    params: dict[str, Any] = {}
    if disaster_id is not None:
        clauses.append("r.disaster_id = :disaster_id")
        params["disaster_id"] = disaster_id
    if incident_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM incident_reports x WHERE x.report_id = r.id AND x.incident_id = :incident_id)"
        )
        params["incident_id"] = incident_id
    for name, values, column in (
        ("channel", channels, "r.source_type"),
        ("status", statuses, "r.processing_status"),
    ):
        if values:
            keys = []
            for index, value in enumerate(values):
                params[f"{name}_{index}"] = value
                keys.append(f":{name}_{index}")
            clauses.append(f"{column} IN ({', '.join(keys)})")
    if search:
        clauses.append("(r.original_text ILIKE :search OR r.translated_text ILIKE :search)")
        params["search"] = f"%{search.strip()}%"
    where = " WHERE " + " AND ".join(clauses)
    total = session.execute(text(f"SELECT count(*) FROM reports r{where}"), params).scalar_one()
    rows = session.execute(
        text(f"{_REPORT_LIST}{where} ORDER BY r.received_at DESC, r.id LIMIT :limit OFFSET :offset"),
        {**params, "limit": limit, "offset": offset},
    ).mappings().all()
    return [dict(r) for r in rows], total


def get_report_row(session: Session, report_id: uuid.UUID) -> Optional[dict[str, Any]]:
    row = session.execute(text(f"{_REPORT_LIST} WHERE r.id = :id"), {"id": report_id}).mappings().first()
    return dict(row) if row else None


def processing_runs(session: Session, report_id: uuid.UUID) -> list[ProcessingRunModel]:
    return list(
        session.execute(
            select(ProcessingRunModel)
            .where(ProcessingRunModel.report_id == report_id)
            .order_by(ProcessingRunModel.created_at.asc())
        ).scalars()
    )


def incident_reference(session: Session, incident_id: uuid.UUID) -> Optional[str]:
    return session.execute(
        select(IncidentModel.reference).where(IncidentModel.id == incident_id)
    ).scalar_one_or_none()
