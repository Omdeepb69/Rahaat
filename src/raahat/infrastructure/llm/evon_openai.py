"""OpenAI-compatible client for Gnani Evon v3.3 reasoning model and local LLM endpoints.

Supports Gnani Evon (30B parameter reasoning model on Hugging Face / vLLM / Ollama),
OpenRouter, or local OpenAI-compatible endpoints with graceful fallback to the
adaptive reasoning engine.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping, Optional

import httpx

from .adaptive_engine import AdaptiveDistressReasoningEngine
from .protocol import EmergencyFactExtraction, LLMClient

logger = logging.getLogger(__name__)

DEFAULT_EVON_MODEL = "gnani/gnani-evon-v3.3-30B-A3B"

SYSTEM_EXTRACTION_PROMPT = """You are Raahat Emergency AI Assistant, handling real-time disaster distress calls in India.
Your mission is to understand the victim's situation dynamically, extract vital facts, and ask the single most important missing question concisely.

Guidelines:
1. Extract location/landmark, number of people trapped, critical hazards (rising floodwaters, roof collapse, chest-deep water), and medical needs.
2. DO NOT ask for information the caller has already provided.
3. If location is missing, ask for location/landmark first.
4. If location is known but headcount is missing, ask how many people are trapped.
5. If location and count are known, ask about immediate injuries, water level, or hazards.
6. If essential facts (location, headcount, and situation) are all known OR caller is in immediate life danger:
   Set "is_completed": true, and provide reassuring final words that rescue teams are dispatched.
7. Output strictly valid JSON matching this schema:
{
  "location_text": string or null,
  "people_count": integer or null,
  "needs": [string],
  "hazards": [string],
  "medical_urgency": boolean,
  "assessed_priority": "P0" | "P1" | "P2" | "P3",
  "situation_summary": string,
  "next_prompt": string (short empathetic response/question in Hindi or Hinglish, suitable for TTS),
  "is_completed": boolean,
  "missing_fields": [string]
}
"""


class EvonOpenAIClient(LLMClient):
    """Client for Gnani Evon v3.3 or any OpenAI-compatible inference server."""

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 12.0,
        fallback_engine: Optional[AdaptiveDistressReasoningEngine] = None,
    ) -> None:
        self.api_base = (
            api_base
            or os.getenv("EVON_API_BASE")
            or os.getenv("OPENAI_API_BASE")
            or "http://localhost:11434/v1"
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("EVON_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "dummy_key"
        )
        self.model = model or os.getenv("EVON_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_EVON_MODEL
        self.timeout_seconds = timeout_seconds
        self.fallback_engine = fallback_engine or AdaptiveDistressReasoningEngine()

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Call chat completion endpoint."""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return str(content)
                logger.warning(
                    "Evon API returned non-200 (%s): %s; falling back",
                    res.status_code,
                    res.text[:200],
                )
        except Exception as exc:
            logger.warning("Evon API call failed: %s; falling back to reasoning engine", exc)

        return await self.fallback_engine.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def extract_and_respond(
        self,
        dialog_history: list[dict[str, str]],
        current_facts: Mapping[str, Any],
        latest_user_utterance: str,
        language_code: str = "hi",
    ) -> EmergencyFactExtraction:
        """Dynamically extract distress entities and formulate the next turn."""
        user_prompt = (
            f"Current known facts: {json.dumps(current_facts, ensure_ascii=False)}\n"
            f"Language code: {language_code}\n"
            f"Dialog history: {json.dumps(dialog_history, ensure_ascii=False)}\n"
            f"Latest caller utterance: \"{latest_user_utterance}\"\n\n"
            f"Respond strictly with the required JSON object."
        )

        try:
            raw_json = await self.generate(
                prompt=user_prompt,
                system_prompt=SYSTEM_EXTRACTION_PROMPT,
                json_mode=True,
                temperature=0.1,
            )
            # Try parsing JSON output
            start = raw_json.find("{")
            end = raw_json.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(raw_json[start : end + 1])
                return EmergencyFactExtraction(
                    location_text=parsed.get("location_text"),
                    people_count=parsed.get("people_count"),
                    needs=parsed.get("needs") or [],
                    hazards=parsed.get("hazards") or [],
                    medical_urgency=bool(parsed.get("medical_urgency", False)),
                    assessed_priority=str(parsed.get("assessed_priority", "P1")),
                    situation_summary=str(parsed.get("situation_summary", "")),
                    next_prompt=str(parsed.get("next_prompt", "")),
                    is_completed=bool(parsed.get("is_completed", False)),
                    missing_fields=parsed.get("missing_fields") or [],
                )
        except Exception as exc:
            logger.warning("Failed to parse LLM extraction JSON: %s; using reasoning engine", exc)

        # Fallback to deterministic semantic extraction
        return await self.fallback_engine.extract_and_respond(
            dialog_history=dialog_history,
            current_facts=current_facts,
            latest_user_utterance=latest_user_utterance,
            language_code=language_code,
        )
