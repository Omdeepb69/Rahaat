"""Gnani Prisma speech-to-text adapter (https://api.vachana.ai/stt/v3).

Request shape follows the adapter that already existed in this repository:
multipart upload with ``audio_file``, ``model``, ``language_code`` and
``format`` fields, authenticated with the ``X-API-Key-ID`` header.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .base import ProviderError, ProviderNotConfigured, Stopwatch, translate_http_errors

PROVIDER = "gnani_prisma"
AUTO_LANGUAGE = "indic-auto"

# Short code -> Prisma locale, as used by the existing integration. Languages
# not listed are sent as automatic detection rather than guessed.
LOCALES = {
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
}


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_ms: Optional[int]
    end_ms: Optional[int]
    confidence: Optional[float]


@dataclass(frozen=True)
class Transcription:
    text: str
    language: Optional[str]
    # None when the provider did not report one. Never defaulted.
    confidence: Optional[float]
    provider: str
    model: str
    duration_ms: float
    segments: tuple[TranscriptSegment, ...] = field(default_factory=tuple)


def sniff_audio(raw: bytes, sample_rate: int = 16000) -> tuple[str, str, bytes]:
    """Return (filename, mime type, payload), wrapping headerless PCM in a WAV container."""
    if raw.startswith(b"RIFF") and b"WAVE" in raw[:16]:
        return "report.wav", "audio/wav", raw
    if raw.startswith(b"ID3") or (len(raw) > 2 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return "report.mp3", "audio/mpeg", raw
    if raw.startswith(b"OggS"):
        return "report.ogg", "audio/ogg", raw
    if raw.startswith(b"\x1a\x45\xdf\xa3"):
        return "report.webm", "audio/webm", raw
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(raw)
    return "report.wav", "audio/wav", buffer.getvalue()


class GnaniPrismaClient:
    name = PROVIDER

    def __init__(
        self,
        *,
        api_key: Optional[str],
        endpoint: str,
        model: str = "prisma-v3.0",
        timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self.model = model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def transcribe(
        self, audio: bytes, *, language_hint: Optional[str] = None, sample_rate: int = 16000
    ) -> Transcription:
        if not self._api_key:
            raise ProviderNotConfigured(PROVIDER, "GNANI_API_KEY_TTS_STT")
        if not audio:
            raise ProviderError(PROVIDER, "no audio supplied")

        filename, mime, payload = sniff_audio(audio, sample_rate)
        language = LOCALES.get((language_hint or "").lower(), AUTO_LANGUAGE)
        watch = Stopwatch()
        with translate_http_errors(PROVIDER):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    self._endpoint,
                    headers={"X-API-Key-ID": self._api_key},
                    files={"audio_file": (filename, payload, mime)},
                    data={"model": self.model, "language_code": language, "format": "transcribe"},
                )
                response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(PROVIDER, "response was not JSON") from exc
        return self._parse(body, watch.elapsed_ms)

    def _parse(self, body: dict[str, Any], duration_ms: float) -> Transcription:
        if not isinstance(body, dict):
            raise ProviderError(PROVIDER, "unexpected response shape")
        text = body.get("transcript")
        if text is None:
            text = body.get("text")
        if not isinstance(text, str):
            raise ProviderError(PROVIDER, "response contained no transcript")

        confidence = body.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) else None
        language = body.get("detected_language_code") or body.get("language") or None

        segments: list[TranscriptSegment] = []
        for seg in body.get("words") or body.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            seg_conf = seg.get("confidence")
            segments.append(
                TranscriptSegment(
                    text=str(seg.get("text") or seg.get("word") or ""),
                    start_ms=int(seg["start_time"] * 1000) if "start_time" in seg else None,
                    end_ms=int(seg["end_time"] * 1000) if "end_time" in seg else None,
                    confidence=float(seg_conf) if isinstance(seg_conf, (int, float)) else None,
                )
            )
        return Transcription(
            text=text.strip(),
            language=str(language) if language else None,
            confidence=confidence,
            provider=PROVIDER,
            model=self.model,
            duration_ms=duration_ms,
            segments=tuple(segments),
        )
