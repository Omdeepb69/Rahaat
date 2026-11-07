"""Piper local TTS adapter for low-latency offline voice synthesis."""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

from .protocol import SynthesisInput, SynthesisOutput, TTSSynthesizer

logger = logging.getLogger(__name__)


class PiperTTS(TTSSynthesizer):
    """Adapter wrapping Piper local neural text-to-speech engine.

    Provides fast, offline speech synthesis for Indian languages (e.g. Hindi, Malayalam)
    in disaster IVR interactions.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        config_path: Optional[str] = None,
        sample_rate: int = 22050,
        voice_instance: Optional[Any] = None,
    ) -> None:
        self.model_path = model_path
        self.config_path = config_path
        self.sample_rate = sample_rate
        self._voice = voice_instance

    def _get_voice(self) -> Any:
        if self._voice is not None:
            return self._voice

        try:
            from piper import PiperVoice  # type: ignore[import-not-found]

            if not self.model_path:
                raise ValueError("PiperTTS requires model_path when voice_instance is not provided.")

            self._voice = PiperVoice.load(self.model_path, config_path=self.config_path)
            return self._voice
        except ImportError as exc:
            raise RuntimeError(
                "PiperTTS requires 'piper-tts' to be installed. "
                "Install it with 'pip install piper-tts' or provide a mock voice_instance."
            ) from exc

    async def synthesize(self, request: SynthesisInput) -> SynthesisOutput:
        """Synthesize text prompt to raw audio bytes (16-bit PCM / WAV)."""
        voice = self._get_voice()

        # Custom/test mock voice hook
        if hasattr(voice, "synthesize_text"):
            raw_audio = voice.synthesize_text(request.text)
            return SynthesisOutput(
                audio_bytes=raw_audio,
                encoding="pcm_s16le",
                sample_rate=self.sample_rate,
            )

        buf = io.BytesIO()
        # Piper's native interface writes to a wave-like or file-like buffer
        voice.synthesize(request.text, buf)
        audio_bytes = buf.getvalue()

        return SynthesisOutput(
            audio_bytes=audio_bytes,
            encoding="wav",
            sample_rate=self.sample_rate,
        )


class MockTTSSynthesizer(TTSSynthesizer):
    """Deterministic in-memory TTS synthesizer for testing."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.synthesized_prompts: list[str] = []

    async def synthesize(self, request: SynthesisInput) -> SynthesisOutput:
        self.synthesized_prompts.append(request.text)
        # Create deterministic dummy bytes based on text length
        dummy_audio = f"[AUDIO:{request.language}:{request.text}]".encode("utf-8")
        return SynthesisOutput(
            audio_bytes=dummy_audio,
            encoding="mock_pcm",
            sample_rate=self.sample_rate,
        )

