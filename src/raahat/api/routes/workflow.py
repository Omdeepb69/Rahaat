"""Workflow orchestration API routes for automated audio triage and dispatch recommendation."""
from __future__ import annotations

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

from raahat.api.dependencies import get_audio_triage_workflow
from raahat.application.workflow import AutomatedAudioTriageWorkflow, WorkflowResult
from raahat.infrastructure.speech import AudioInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])


class WorkflowCoordinates(BaseModel):
    """Geographic point coordinates in workflow output."""

    latitude: float
    longitude: float


class WorkflowExecutionResponse(BaseModel):
    """Detailed response for an automated audio triage pipeline execution."""

    report_id: uuid.UUID
    incident_id: uuid.UUID
    disaster_id: uuid.UUID
    transcript: str
    confidence: float
    has_speech: bool
    priority: str
    priority_reasons: list[str]
    is_new_incident: bool
    proposed_resource_id: Optional[uuid.UUID] = None
    proposed_resource_name: Optional[str] = None
    location_label: Optional[str] = None
    coordinates: Optional[WorkflowCoordinates] = None
    uncertainty_radius_m: Optional[float] = None
    execution_time_ms: float = Field(..., description="Pipeline execution duration in milliseconds")


def _result_to_response(result: WorkflowResult) -> WorkflowExecutionResponse:
    coords = None
    if result.coordinates is not None:
        coords = WorkflowCoordinates(
            latitude=result.coordinates.latitude,
            longitude=result.coordinates.longitude,
        )

    return WorkflowExecutionResponse(
        report_id=result.report_id,
        incident_id=result.incident_id,
        disaster_id=result.disaster_id,
        transcript=result.transcript,
        confidence=result.confidence,
        has_speech=result.has_speech,
        priority=result.priority.value,
        priority_reasons=list(result.priority_reasons),
        is_new_incident=result.is_new_incident,
        proposed_resource_id=result.proposed_resource_id,
        proposed_resource_name=result.proposed_resource_name,
        location_label=result.location_label,
        coordinates=coords,
        uncertainty_radius_m=result.uncertainty_radius_m,
        execution_time_ms=result.execution_time_ms,
    )


@router.post(
    "/audio-triage",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute end-to-end automated audio triage and dispatch proposal from audio file",
)
async def execute_audio_triage(
    audio_file: UploadFile = File(..., description="Audio distress note file (wav, webm, mp3)"),
    disaster_id: uuid.UUID = Form(..., description="Active disaster context identifier"),
    caller_phone: Optional[str] = Form(None, description="Optional caller phone number"),
    latitude: Optional[float] = Form(None, description="Optional caller GPS latitude"),
    longitude: Optional[float] = Form(None, description="Optional caller GPS longitude"),
    language_hint: Optional[str] = Form(None, description="Optional Indic speech language hint (mr, hi, en)"),
    workflow: AutomatedAudioTriageWorkflow = Depends(get_audio_triage_workflow),
) -> WorkflowExecutionResponse:
    """Execute the end-to-end Automated Audio-to-Dispatch Orchestrator pipeline on distress audio:

    1. Speech transcription & Voice Activity Detection (Whisper/fallback)
    2. PostGIS spatial landmark disambiguation
    3. Structured evidence extraction and report linking
    4. Canonical incident resolution
    5. Deterministic safety policy triage (P0-P3)
    6. Nearest rescue resource recommendation (PROPOSED)
    7. Real-time live SSE broadcast to dispatcher consoles
    8. Citizen tracking ticket status advancement
    """
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty",
        )

    audio_input = AudioInput(
        audio_bytes=audio_bytes,
        sample_rate=16000,
    )

    caller_info: dict[str, Any] = {}
    if caller_phone:
        caller_info["caller_phone"] = caller_phone
        caller_info["source_identity"] = caller_phone
    if latitude is not None and longitude is not None:
        caller_info["latitude"] = latitude
        caller_info["longitude"] = longitude
    if language_hint:
        caller_info["language_hint"] = language_hint

    try:
        result = await workflow.run(
            audio_input=audio_input,
            disaster_id=disaster_id,
            caller_info=caller_info,
        )
    except Exception as e:
        logger.error("Audio triage workflow execution failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow failed: {e}",
        )

    return _result_to_response(result)


@router.post(
    "/reports/{report_id}/run",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute automated triage and dispatch recommendation for an existing report",
)
async def execute_workflow_for_report(
    report_id: uuid.UUID,
    workflow: AutomatedAudioTriageWorkflow = Depends(get_audio_triage_workflow),
) -> WorkflowExecutionResponse:
    """Run downstream triage and dispatch orchestration for an existing report ticket."""
    try:
        result = await workflow.run_for_report(report_id=report_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Workflow execution for report %s failed: %s", report_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow failed: {e}",
        )

    return _result_to_response(result)
