"""Chat-completion clients that return a parsed JSON object.

Two wire formats are supported: OpenAI-compatible chat completions (used for
Gnani Evon behind vLLM, TGI or a hosted gateway) and the Google Gemini
``generateContent`` API. Both expose the same ``complete_json`` method so the
application layer does not depend on either.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional, Protocol

import httpx

from .base import ProviderError, ProviderNotConfigured, Stopwatch, translate_http_errors


@dataclass(frozen=True)
class JsonCompletion:
    data: dict[str, Any]
    provider: str
    model: str
    duration_ms: float


class JsonModelClient(Protocol):
    name: str
    model: str

    @property
    def configured(self) -> bool: ...

    def complete_json(self, *, system: str, user: str, max_tokens: int = 1024) -> JsonCompletion: ...


def _parse_json_object(provider: str, text: str) -> dict[str, Any]:
    """Parse a model reply as one JSON object, tolerating a Markdown code fence."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderError(provider, "model reply was not a JSON object")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError(provider, f"model reply was not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError(provider, "model reply was not a JSON object")
    return parsed


class OpenAICompatibleClient:
    """Gnani Evon (or any model) served through an OpenAI-compatible endpoint."""

    name = "evon"

    def __init__(
        self,
        *,
        api_base: Optional[str],
        api_key: Optional[str],
        model: str,
        timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._api_base = api_base.rstrip("/") if api_base else None
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_base)

    def complete_json(self, *, system: str, user: str, max_tokens: int = 1024) -> JsonCompletion:
        if not self._api_base:
            raise ProviderNotConfigured(self.name, "EVON_API_BASE")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        watch = Stopwatch()
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self._api_base}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc
        return JsonCompletion(
            data=_parse_json_object(self.name, str(content)),
            provider=self.name,
            model=self.model,
            duration_ms=watch.elapsed_ms,
        )


class GeminiClient:
    name = "gemini"
    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        *,
        api_key: Optional[str],
        model: str,
        timeout_seconds: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def complete_json(self, *, system: str, user: str, max_tokens: int = 1024) -> JsonCompletion:
        if not self._api_key:
            raise ProviderNotConfigured(self.name, "GEMINI_API_KEY")
        watch = Stopwatch()
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self._BASE}/{self.model}:generateContent",
                    # The key travels in a header so it never appears in URLs or logs.
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {
                            "temperature": 0,
                            "maxOutputTokens": max_tokens,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                response.raise_for_status()
        try:
            body = response.json()
            parts = body["candidates"][0]["content"]["parts"]
            content = "".join(str(p.get("text", "")) for p in parts)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc
        return JsonCompletion(
            data=_parse_json_object(self.name, content),
            provider=self.name,
            model=self.model,
            duration_ms=watch.elapsed_ms,
        )
