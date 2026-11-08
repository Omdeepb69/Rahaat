"""Gnani Timbre Text-to-Speech (TTS) adapter.

Integrates with Gnani Timbre API (https://api.vachana.ai/api/v1/tts/inference)
for expressive, natural speech synthesis across 10 Indian languages.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .protocol import SynthesisInput, SynthesisOutput, TTSSynthesizer

logger = logging.getLogger(__name__)

DEFAULT_TIMBRE_ENDPOINT = "https://api.vachana.ai/api/v1/tts/inference"

_TTS_LANGUAGE_MAP = {
    "hi": "hi-IN",
    "en": "en-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "bn": "bn-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
    "hi-en": "hi-en",
    "auto": "auto",
}


class GnaniTimbreTTS(TTSSynthesizer):
    """Client adapter for Gnani Timbre TTS service.

    Provides low-latency, natural Indic speech synthesis for conversational emergency IVR.
    """

    def __init__(
        self,
        endpoint_url: str = DEFAULT_TIMBRE_ENDPOINT,
        api_key: Optional[str] = None,
        model: str = "timbre-v3.0",
        voice: str = "Shivani",
        default_language: str = "auto",
        speed: float = 1.0,
        sample_rate: int = 16000,
        timeout_seconds: float = 15.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key or os.getenv("GNANI_API_KEY_TTS_STT") or os.getenv("GNANI_API_KEY")
        self.model = model
        self.voice = voice
        self.default_language = default_language
        self.speed = speed
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client

    def _map_language(self, lang: Optional[str]) -> str:
        if not lang:
            return self.default_language
        return _TTS_LANGUAGE_MAP.get(lang, lang)

    async def synthesize(self, request: SynthesisInput) -> SynthesisOutput:
        """Synthesize text into WAV audio using Gnani Timbre."""
        lang = self._map_language(request.language)

        if self._http_client is not None:
            raw_audio = await self._http_client.post(
                self.endpoint_url,
                text=request.text,
                language=lang,
                voice=self.voice,
                model=self.model,
            )
            if isinstance(raw_audio, dict) and "audio_bytes" in raw_audio:
                return SynthesisOutput(
                    audio_bytes=raw_audio["audio_bytes"],
                    encoding="wav",
                    sample_rate=self.sample_rate,
                )
            return SynthesisOutput(
                audio_bytes=raw_audio if isinstance(raw_audio, bytes) else b"[MOCK_WAV]",
                encoding="wav",
                sample_rate=self.sample_rate,
            )

        if not self.api_key:
            logger.warning("GnaniTimbreTTS called without API key; returning mock audio bytes")
            # Deterministic dummy WAV header + PCM for offline fallback
            mock_pcm = f"[TIMBRE_MOCK:{lang}:{request.text}]".encode("utf-8")
            return SynthesisOutput(
                audio_bytes=mock_pcm,
                encoding="wav",
                sample_rate=self.sample_rate,
            )

        try:
            import httpx

            headers = {
                "X-API-Key-ID": self.api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "text": request.text,
                "model": self.model,
                "voice": self.voice,
                "language": lang,
                "speed": self.speed,
                "audio_config": {
                    "sample_rate": self.sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": "wav",
                },
            }

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(
                    self.endpoint_url,
                    json=payload,
                    headers=headers,
                )
                res.raise_for_status()
                return SynthesisOutput(
                    audio_bytes=res.content,
                    encoding="wav",
                    sample_rate=self.sample_rate,
                )
        except Exception as exc:
            logger.error("Gnani Timbre TTS synthesis failed: %s", exc)
            raise RuntimeError(f"Gnani Timbre TTS request failed: {exc}") from exc
