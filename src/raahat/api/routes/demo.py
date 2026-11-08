"""Demo orchestration API route — executes a pre-seeded scenario step."""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from raahat.api.dependencies import get_audio_triage_workflow
from raahat.api.routes.workflow import WorkflowExecutionResponse, _result_to_response
from raahat.application.workflow import AutomatedAudioTriageWorkflow
from raahat.infrastructure.speech import AudioInput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

_DEFAULT_WAV_DIR = (
    Path(__file__).resolve().parents[4] / "demo" / "audio" / "kerala_2018_wav"
)


def _get_wav_files() -> list[Path]:
    override = os.getenv("DEMO_AUDIO_DIR")
    directory = Path(override) if override else _DEFAULT_WAV_DIR
    if directory.exists():
        return sorted(directory.glob("*.wav"))
    return []


class DemoRunRequest(BaseModel):
    """Request body for a single-step demo scenario execution."""

    disaster_id: uuid.UUID
    audio_index: int = 0
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    language_hint: str = "ml"


@router.post(
    "/run-scenario",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute one audio triage step from the Kerala 2018 archival flood recordings",
)
async def run_demo_scenario(
    body: DemoRunRequest,
    workflow: AutomatedAudioTriageWorkflow = Depends(get_audio_triage_workflow),
) -> WorkflowExecutionResponse:
    """Execute the automated audio triage pipeline on one Kerala 2018 archival recording.

    The ``audio_index`` cycles through the available WAV files so the caller can
    advance through each recording in sequence (0 → len-1 → wraps).

    Audio provenance: Kerala Flood 2018 archival recordings, Christ College
    Irinjalakuda DSpace repository. These are flood-era archival voice notes,
    not confirmed victim-to-helpline calls.
    """
    wav_files = _get_wav_files()
    if not wav_files:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Kerala 2018 audio files not found. "
                "Run: ffmpeg conversion in demo/audio/kerala_2018_wav/ first."
            ),
        )

    wav_path = wav_files[body.audio_index % len(wav_files)]
    logger.info("Demo: loading audio file %s (index %d)", wav_path.name, body.audio_index)

    audio_bytes = wav_path.read_bytes()
    audio_input = AudioInput(audio_bytes=audio_bytes, sample_rate=16000)

    caller_info: dict[str, Any] = {"language_hint": body.language_hint}
    if body.latitude is not None and body.longitude is not None:
        caller_info["latitude"] = body.latitude
        caller_info["longitude"] = body.longitude

    try:
        result = await workflow.run(
            audio_input=audio_input,
            disaster_id=body.disaster_id,
            caller_info=caller_info,
        )
    except Exception as exc:
        logger.error("Demo workflow failed on %s: %s", wav_path.name, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Demo workflow failed: {exc}",
        )

    return _result_to_response(result)

