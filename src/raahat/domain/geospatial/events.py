"""Event envelopes for location and streaming events."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional, Sequence, Tuple, Union

import numpy as np

SUBJECT_TRANSCRIPT = "calls.{call_id}.transcript"
SUBJECT_FACTS = "calls.{call_id}.facts"
SUBJECT_LOCATION = "calls.{call_id}.location"
SUBJECT_INCIDENT = "incidents.updated"
SUBJECT_DISPATCH = "dispatch.proposed"


@dataclass
class Evidence:
    """Pointer back to the audio/transcript span that supports a fact."""

    call_id: str
    t_start: float
    t_end: float
    text: str
    asr_conf: Optional[float] = None


@dataclass
class Envelope:
    type: str
    data: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    time: float = field(default_factory=time.time)
    source: str = "raahat"
    specversion: str = "1.0"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> Envelope:
        return cls(**json.loads(raw))


def transcript_segment(
    call_id: str, text: str, is_final: bool, t0: float, t1: float
) -> Envelope:
    return Envelope(
        "raahat.transcript.segment",
        {
            "call_id": call_id,
            "text": text,
            "final": is_final,
            "t_start": t0,
            "t_end": t1,
        },
    )


def fact_extracted(
    call_id: str, field_name: str, value: Any, evidence: Evidence, confidence: float
) -> Envelope:
    return Envelope(
        "raahat.fact.extracted",
        {
            "call_id": call_id,
            "field": field_name,
            "value": value,
            "confidence": confidence,
            "evidence": asdict(evidence),
        },
    )


def location_updated(
    call_id: str,
    xy: Union[Sequence[float], np.ndarray, Tuple[float, float]],
    confidence: float,
    entropy: float,
    question: Optional[List[Any]],
) -> Envelope:
    return Envelope(
        "raahat.location.updated",
        {
            "call_id": call_id,
            "estimate_xy": [float(xy[0]), float(xy[1])],
            "confidence": confidence,
            "entropy": entropy,
            "question": question,
        },
    )
