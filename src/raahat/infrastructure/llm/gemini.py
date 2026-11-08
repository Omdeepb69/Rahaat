"""Google Gemini LLM client for real-time disaster distress understanding and dynamic dialogue."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping, Optional

import httpx

from .adaptive_engine import AdaptiveDistressReasoningEngine
from .evon_openai import SYSTEM_EXTRACTION_PROMPT
from .protocol import EmergencyFactExtraction, LLMClient

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiLLMClient(LLMClient):
    """Client for Google Gemini (Flash / Flash-Lite) inference."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 12.0,
        fallback_engine: Optional[AdaptiveDistressReasoningEngine] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
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
        """Call Gemini generateContent endpoint."""
        if not self.api_key:
            logger.debug("No GEMINI_API_KEY set; using adaptive reasoning fallback")
            return await self.fallback_engine.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                json_mode=json_mode,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        url = f"{GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"
        contents: list[dict[str, Any]] = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nPlease follow these instructions strictly."}],
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will act strictly as the Raahat Emergency AI Assistant."}],
            })

        contents.append({
            "role": "user",
            "parts": [{"text": prompt}],
        })

        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": contents,
            "generationConfig": gen_config,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                res = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return str(parts[0].get("text", ""))
                logger.warning(
                    "Gemini API returned HTTP %s (%s); falling back to adaptive reasoning",
                    res.status_code,
                    res.text[:120],
                )
        except Exception as exc:
            logger.warning("Gemini API call failed: %s; falling back to adaptive reasoning", exc)

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
        """Dynamically extract distress entities and formulate the next turn via Gemini."""
        if not self.api_key:
            return await self.fallback_engine.extract_and_respond(
                dialog_history=dialog_history,
                current_facts=current_facts,
                latest_user_utterance=latest_user_utterance,
                language_code=language_code,
            )

        user_prompt = (
            f"Current known facts: {json.dumps(dict(current_facts), ensure_ascii=False)}\n"
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
            logger.warning("Gemini extraction parsing failed: %s; using adaptive engine", exc)

        return await self.fallback_engine.extract_and_respond(
            dialog_history=dialog_history,
            current_facts=current_facts,
            latest_user_utterance=latest_user_utterance,
            language_code=language_code,
        )
