"""Gnani Timbre text-to-speech adapter (https://api.vachana.ai/api/v1/tts/inference).

Returns WAV audio. Synthesised prompts are cached on disk by a hash of
(model, voice, language, text), so a fixed question is synthesised once.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx

from .base import ProviderError, ProviderNotConfigured, translate_http_errors

PROVIDER = "gnani_timbre"

LOCALES = {
    "hi": "hi-IN", "en": "en-IN", "ml": "ml-IN", "mr": "mr-IN", "ta": "ta-IN",
    "te": "te-IN", "kn": "kn-IN", "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN",
}


class GnaniTimbreClient:
    name = PROVIDER

    def __init__(
        self,
        *,
        api_key: Optional[str],
        endpoint: str,
        model: str,
        voice: str,
        cache_dir: Path,
        timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self.model = model
        self.voice = voice
        self._cache_dir = cache_dir
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _cache_path(self, language: str, text: str) -> Path:
        key = hashlib.sha256(f"{self.model}|{self.voice}|{language}|{text}".encode()).hexdigest()
        return self._cache_dir / f"{key}.wav"

    def synthesize(self, text: str, *, language: str) -> bytes:
        """WAV bytes (16 kHz mono) for ``text`` spoken in ``language`` (short code)."""
        if not self._api_key:
            raise ProviderNotConfigured(PROVIDER, "GNANI_API_KEY_TTS_STT")
        text = text.strip()
        if not text:
            raise ProviderError(PROVIDER, "nothing to speak")
        locale = LOCALES.get(language, "auto")
        cached = self._cache_path(locale, text)
        if cached.is_file():
            return cached.read_bytes()
        body = {
            "text": text,
            "model": self.model,
            "voice": self.voice,
            "language": locale,
            "audio_config": {
                "sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                "encoding": "linear_pcm", "container": "wav",
            },
        }
        with translate_http_errors(PROVIDER):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    self._endpoint, json=body, headers={"X-API-Key-ID": self._api_key}
                )
                response.raise_for_status()
        audio = response.content
        if not audio.startswith(b"RIFF"):
            raise ProviderError(PROVIDER, "response was not WAV audio")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._cache_dir, suffix=".part")
        with os.fdopen(fd, "wb") as handle:
            handle.write(audio)
        os.replace(tmp, cached)
        return audio
