"""Local Hugging Face transformers LLM client for CPU/GPU on-device inference."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping, Optional

from .adaptive_engine import AdaptiveDistressReasoningEngine
from .evon_openai import SYSTEM_EXTRACTION_PROMPT
from .protocol import EmergencyFactExtraction, LLMClient

logger = logging.getLogger(__name__)

DEFAULT_LOCAL_MODEL = "HuggingFaceTB/SmolLM-135M"


class LocalTransformersLLMClient(LLMClient):
    """Executes a small open-weight LLM locally via Hugging Face transformers."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        device: str = "cpu",
        fallback_engine: Optional[AdaptiveDistressReasoningEngine] = None,
    ) -> None:
        self.model_id = model_id or os.getenv("LOCAL_LLM_MODEL_ID", DEFAULT_LOCAL_MODEL)
        self.device = device
        self.fallback_engine = fallback_engine or AdaptiveDistressReasoningEngine()
        self._pipeline: Optional[Any] = None
        self._load_attempted = False

    def _ensure_pipeline(self) -> Optional[Any]:
        if self._load_attempted:
            return self._pipeline

        self._load_attempted = True
        try:
            from transformers import pipeline

            logger.info("Initializing local transformers LLM pipeline: %s on %s", self.model_id, self.device)
            self._pipeline = pipeline(
                "text-generation",
                model=self.model_id,
                device=self.device,
                max_new_tokens=256,
            )
            return self._pipeline
        except Exception as exc:
            logger.warning("Could not initialize local transformers LLM (%s): %s; using reasoning fallback", self.model_id, exc)
            self._pipeline = None
            return None

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        pipe = self._ensure_pipeline()
        if pipe is not None:
            try:
                full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                res = pipe(full_prompt, max_new_tokens=max_tokens, do_sample=(temperature > 0))
                gen_text = res[0].get("generated_text", "")
                return str(gen_text[len(full_prompt) :].strip())
            except Exception as exc:
                logger.warning("Local generation failed: %s; falling back", exc)

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
        # If pipeline is loaded and capable of instruction following, generate
        pipe = self._ensure_pipeline()
        if pipe is not None:
            user_prompt = (
                f"Current known facts: {json.dumps(current_facts, ensure_ascii=False)}\n"
                f"Latest caller utterance: \"{latest_user_utterance}\"\n"
                f"Respond with JSON:"
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
                logger.warning("Local transformer extraction parse failed: %s", exc)

        return await self.fallback_engine.extract_and_respond(
            dialog_history=dialog_history,
            current_facts=current_facts,
            latest_user_utterance=latest_user_utterance,
            language_code=language_code,
        )
