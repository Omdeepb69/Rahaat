"""Mock speech recognizer for deterministic testing and offline simulation."""
from __future__ import annotations

from typing import Optional

from .protocol import AudioInput, Transcript


class MockSpeechRecognizer:
    """Configurable SpeechRecognizer implementation for testing."""

    def __init__(
        self,
        default_text: str = "",
        default_confidence: float = 0.95,
        default_language: str = "hi",
    ) -> None:
        self.default_text = default_text
        self.default_confidence = default_confidence
        self.default_language = default_language
        self.transcription_queue: list[Transcript] = []

    def queue_transcript(
        self,
        text: str,
        confidence: float = 0.95,
        language: Optional[str] = None,
    ) -> None:
        self.transcription_queue.append(
            Transcript(
                text=text,
                confidence=confidence,
                language=language or self.default_language,
            )
        )

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript:
        if self.transcription_queue:
            return self.transcription_queue.pop(0)

        # If audio_bytes can be decoded as utf-8 (for easy test mocking), use it
        try:
            decoded = audio.audio_bytes.decode("utf-8")
            if "\x00" not in decoded and decoded.strip():
                return Transcript(
                    text=decoded.strip(),
                    confidence=self.default_confidence,
                    language=language_hint or self.default_language,
                )
        except Exception:
            pass

        return Transcript(
            text=self.default_text,
            confidence=self.default_confidence,
            language=language_hint or self.default_language,
        )
