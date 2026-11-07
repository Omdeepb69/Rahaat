"""Whisper local speech recognizer adapter.

Isolates openai-whisper / faster-whisper dependency behind the SpeechRecognizer protocol.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, cast

from .protocol import AudioInput, SpeechRecognizer, Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class WhisperRecognizer(SpeechRecognizer):
    """Adapter wrapping OpenAI Whisper / faster-whisper models.

    Designed for decoupled execution; does not fail at import time if
    whisper is not installed, but raises a descriptive RuntimeError if invoked
    without the runtime library present.
    """

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        model_instance: Optional[Any] = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._model = model_instance

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            import whisper  # type: ignore[import-not-found]

            self._model = whisper.load_model(self.model_name, device=self.device)
            return self._model
        except ImportError as exc:
            raise RuntimeError(
                "WhisperRecognizer requires 'openai-whisper' to be installed. "
                "Install it with 'pip install openai-whisper' or provide a pre-loaded model_instance."
            ) from exc

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript:
        """Transcribe audio input using Whisper."""
        model = self._get_model()

        # In case a custom/mock model instance is passed (e.g. for unit testing)
        if hasattr(model, "transcribe_audio"):
            return cast(Transcript, await model.transcribe_audio(audio, language_hint=language_hint))

        import numpy as np

        # Convert raw PCM bytes (16-bit signed LE, 16kHz) to float32 numpy array
        # normalized to [-1.0, 1.0] as expected by whisper
        audio_data = np.frombuffer(audio.audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        options: dict[str, Any] = {}
        if language_hint:
            options["language"] = language_hint

        result = model.transcribe(audio_data, **options)

        segments = []
        for seg in result.get("segments", []):
            segments.append(
                TranscriptSegment(
                    text=seg.get("text", "").strip(),
                    confidence=float(np.exp(seg.get("avg_logprob", 0.0))) if "avg_logprob" in seg else 0.8,
                    start_ms=int(seg.get("start", 0) * 1000),
                    end_ms=int(seg.get("end", 0) * 1000),
                    language=result.get("language", language_hint),
                )
            )

        text = result.get("text", "").strip()
        confidence = float(np.mean([s.confidence for s in segments])) if segments else 0.8

        return Transcript(
            text=text,
            confidence=confidence,
            language=result.get("language", language_hint),
            segments=tuple(segments),
        )
