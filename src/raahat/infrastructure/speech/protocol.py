"""Speech recognition and TTS protocols and value objects."""
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


@dataclass(frozen=True)
class SynthesisInput:
    """Text to synthesise into speech."""

    text: str
    language: str = "hi"
    speaking_rate: float = 1.0


@dataclass(frozen=True)
class SynthesisOutput:
    """Raw audio produced by a TTS adapter."""

    audio_bytes: bytes
    # Encoding description e.g. "pcm_s16le_22050hz"
    encoding: str
    sample_rate: int


class SpeechRecognizer(Protocol):
    """Protocol for speech-to-text models (Whisper, Gnani Prisma, etc.).

    Implementations must be decoupled from core domain logic.
    """

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript: ...


class TTSSynthesizer(Protocol):
    """Protocol for text-to-speech engines (Piper, cloud TTS, etc.).

    Implementations must be decoupled from core domain logic.
    """

    async def synthesize(self, request: SynthesisInput) -> SynthesisOutput: ...
