"""Speech recognition protocols and value objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class AudioInput:
    """Raw audio data submitted for VAD or speech recognition."""

    audio_bytes: bytes
    sample_rate: int = 16000
    duration_ms: Optional[int] = None


@dataclass(frozen=True)
class TranscriptSegment:
    """A segment or phrase within a transcription."""

    text: str
    confidence: float
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    language: Optional[str] = None


@dataclass(frozen=True)
class Transcript:
    """Complete transcription output with confidence and optional segmentation."""

    text: str
    confidence: float
    language: Optional[str] = None
    segments: tuple[TranscriptSegment, ...] = field(default_factory=tuple)


class SpeechRecognizer(Protocol):
    """Protocol for speech-to-text models (Whisper, Gnani Prisma, etc.).

    Implementations must be decoupled from core domain logic.
    """

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript: ...
