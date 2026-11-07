"""Gnani Prisma speech recognition adapter stub.

Integrates with Gnani Prisma ASR API for Indian languages (Hindi, Malayalam, Tamil, etc.).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .protocol import AudioInput, SpeechRecognizer, Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class PrismaRecognizer(SpeechRecognizer):
    """Client adapter for Gnani Prisma ASR service.

    Provides high-accuracy regional Indian language transcription tuned for noisy
    telephony audio and conversational code-mixing.
    """

    def __init__(
        self,
        endpoint_url: str = "https://api.gnani.ai/asr/v1/recognize",
        api_key: Optional[str] = None,
        default_language: str = "hi",
        timeout_seconds: float = 10.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.default_language = default_language
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def transcribe(
        self,
        audio: AudioInput,
        language_hint: Optional[str] = None,
    ) -> Transcript:
        """Transcribe audio using Gnani Prisma ASR."""
        language = language_hint or self.default_language

        if self._http_client is not None:
            # Used in testing or custom dependency-injected client
            response = await self._http_client.post(
                self.endpoint_url,
                audio_bytes=audio.audio_bytes,
                language=language,
                sample_rate=audio.sample_rate,
            )
            return self._parse_prisma_response(response, fallback_language=language)

        if not self.api_key:
            logger.warning("PrismaRecognizer called without API key; returning stub transcript")
            return Transcript(
                text="",
                confidence=0.0,
                language=language,
                segments=(),
            )

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "audio/x-raw",
                "X-Language-Code": language,
                "X-Sample-Rate": str(audio.sample_rate),
            }

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(
                    self.endpoint_url,
                    content=audio.audio_bytes,
                    headers=headers,
                )
                res.raise_for_status()
                data = res.json()
                return self._parse_prisma_response(data, fallback_language=language)
        except Exception as exc:
            logger.error("Prisma ASR transcription failed: %s", exc)
            raise RuntimeError(f"Gnani Prisma transcription request failed: {exc}") from exc

    def _parse_prisma_response(self, data: dict[str, Any], fallback_language: str) -> Transcript:
        """Parse Gnani Prisma JSON response format into Raahat Transcript."""
        transcript_text = data.get("transcript", "") or data.get("text", "")
        overall_confidence = float(data.get("confidence", 0.85))
        lang = data.get("language", fallback_language)

        raw_segments = data.get("words", []) or data.get("segments", [])
        segments: list[TranscriptSegment] = []

        for seg in raw_segments:
            segments.append(
                TranscriptSegment(
                    text=seg.get("text", "") or seg.get("word", ""),
                    confidence=float(seg.get("confidence", overall_confidence)),
                    start_ms=int(seg.get("start_time", 0) * 1000) if "start_time" in seg else None,
                    end_ms=int(seg.get("end_time", 0) * 1000) if "end_time" in seg else None,
                    language=lang,
                )
            )

        return Transcript(
            text=transcript_text.strip(),
            confidence=overall_confidence,
            language=lang,
            segments=tuple(segments),
        )

