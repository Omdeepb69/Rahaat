"""Gnani Prisma v3.0 speech recognition adapter.

Integrates with Gnani Prisma v3.0 ASR API (https://api.vachana.ai/stt/v3)
for Indian languages (Hindi, Malayalam, Marathi, Tamil, English, and Hinglish).
"""
from __future__ import annotations

import io
import json
import logging
import os
import wave
from typing import Any, Optional

from .protocol import AudioInput, SpeechRecognizer, Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

DEFAULT_PRISMA_ENDPOINT = "https://api.vachana.ai/stt/v3"

_LANGUAGE_CODE_MAP = {
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

DEFAULT_EMERGENCY_KEYTERMS = [
    "नाव",
    "boat",
    "NDRF",
    "Shaniwar Wada",
    "Bund Garden",
    "Alappuzha",
    "Ernakulam",
    "paani",
    "vellam",
    "trapped",
    "madat",
    "rescue",
    "hospital",
    "oxygen",
    "first floor",
    "chhat",
]


class PrismaRecognizer(SpeechRecognizer):
    """Client adapter for Gnani Prisma v3.0 ASR service.

    Provides high-accuracy regional Indian language transcription tuned for noisy
    telephony audio and conversational code-mixing.
    """

    def __init__(
        self,
        endpoint_url: str = DEFAULT_PRISMA_ENDPOINT,
        api_key: Optional[str] = None,
        default_language: str = "indic-auto",
        model: str = "prisma-v3.0",
        output_format: str = "transcribe",
        topic: Optional[str] = "Disaster emergency distress call, flood rescue, trapped people",
        keyterms: Optional[list[str]] = None,
        timeout_seconds: float = 30.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key or os.getenv("GNANI_API_KEY_TTS_STT") or os.getenv("GNANI_API_KEY")
        self.default_language = default_language
        self.model = model
        self.output_format = output_format
        self.topic = topic
        self.keyterms = keyterms or DEFAULT_EMERGENCY_KEYTERMS
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client

    def _normalize_language_code(self, lang: Optional[str]) -> str:
        """Map short language codes ('hi', 'ml') to Gnani locales ('hi-IN', 'ml-IN')."""
        if not lang:
            return self.default_language
        if lang in _LANGUAGE_CODE_MAP:
            return _LANGUAGE_CODE_MAP[lang]
        return lang

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript:
        """Transcribe audio using Gnani Prisma ASR."""
        raw_lang = language_hint or self.default_language
        language = self._normalize_language_code(raw_lang)

        if self._http_client is not None:
            # Used in unit tests or custom dependency-injected client
            response = await self._http_client.post(
                self.endpoint_url,
                audio_bytes=audio.audio_bytes,
                language=language,
                sample_rate=audio.sample_rate,
            )
            return self._parse_prisma_response(response, fallback_language=raw_lang or "und")

        if not self.api_key:
            logger.warning("PrismaRecognizer called without API key; returning stub transcript")
            return Transcript(
                text="",
                confidence=0.0,
                language=raw_lang or "und",
                segments=(),
            )

        try:
            import httpx

            headers = {
                "X-API-Key-ID": self.api_key,
            }

            # Determine container format and MIME type
            raw_bytes = audio.audio_bytes
            filename = "emergency_call.wav"
            mime_type = "audio/wav"

            if raw_bytes.startswith(b"ID3") or (len(raw_bytes) > 2 and raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0):
                filename = "emergency_call.mp3"
                mime_type = "audio/mpeg"
                payload_bytes = raw_bytes
            elif raw_bytes.startswith(b"OggS") or raw_bytes.startswith(b"\x1a\x45\xdf\xa3"):
                filename = "emergency_call.webm"
                mime_type = "audio/webm"
                payload_bytes = raw_bytes
            elif raw_bytes.startswith(b"RIFF") and b"WAVE" in raw_bytes[:16]:
                filename = "emergency_call.wav"
                mime_type = "audio/wav"
                payload_bytes = raw_bytes
            else:
                # Raw PCM: wrap in standard 16-bit mono WAV header
                try:
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(audio.sample_rate or 16000)
                        wf.writeframes(raw_bytes)
                    payload_bytes = buf.getvalue()
                except Exception as pcm_err:
                    logger.warning("Could not wrap audio into WAV header: %s", pcm_err)
                    payload_bytes = raw_bytes

            files = {
                "audio_file": (filename, payload_bytes, mime_type),
            }

            data: dict[str, Any] = {
                "model": self.model,
                "language_code": language,
                "format": self.output_format,
            }

            if self.topic:
                data["topic"] = self.topic[:1600]

            if self.keyterms:
                data["keyterms"] = json.dumps(self.keyterms[:200], ensure_ascii=False)

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(
                    self.endpoint_url,
                    files=files,
                    data=data,
                    headers=headers,
                )
                res.raise_for_status()
                data_res = res.json()
                return self._parse_prisma_response(data_res, fallback_language=raw_lang or "und")
        except Exception as exc:
            logger.error("Prisma ASR transcription failed: %s; returning empty fallback transcript", exc)
            return Transcript(
                text="",
                confidence=0.0,
                language=raw_lang or "und",
                segments=(),
            )

    def _parse_prisma_response(self, data: dict[str, Any], fallback_language: str) -> Transcript:
        """Parse Gnani Prisma JSON response format into Raahat Transcript."""
        transcript_text = data.get("transcript", "") or data.get("text", "")
        overall_confidence = float(data.get("confidence", 0.92))
        detected_lang = (
            data.get("detected_language_code")
            or data.get("language")
            or fallback_language
        )

        raw_segments = data.get("words", []) or data.get("segments", [])
        segments: list[TranscriptSegment] = []

        for seg in raw_segments:
            segments.append(
                TranscriptSegment(
                    text=seg.get("text", "") or seg.get("word", ""),
                    confidence=float(seg.get("confidence", overall_confidence)),
                    start_ms=int(seg.get("start_time", 0) * 1000) if "start_time" in seg else None,
                    end_ms=int(seg.get("end_time", 0) * 1000) if "end_time" in seg else None,
                    language=detected_lang,
                )
            )

        return Transcript(
            text=transcript_text.strip(),
            confidence=overall_confidence,
            language=detected_lang,
            segments=tuple(segments),
        )
