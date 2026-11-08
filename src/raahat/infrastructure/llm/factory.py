"""Factory for creating LLM and reasoning clients based on environment configuration."""
from __future__ import annotations

import os
from typing import Optional

from .adaptive_engine import AdaptiveDistressReasoningEngine
from .evon_openai import EvonOpenAIClient
from .local_transformers import LocalTransformersLLMClient
from .protocol import LLMClient


def create_llm_client(
    provider: Optional[str] = None,
    api_base: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMClient:
    """Create an LLMClient instance according to environment or explicit arguments.

    Order of evaluation:
    1. If provider == "openai" or "evon", or EVON_API_BASE is set -> EvonOpenAIClient
    2. If provider == "transformers" or USE_LOCAL_TRANSFORMERS == "true" -> LocalTransformersLLMClient
    3. Default -> AdaptiveDistressReasoningEngine (zero-latency, highly accurate on Indic disaster entities)
    """
    selected_provider = (provider or os.getenv("LLM_PROVIDER") or "").lower()

    if selected_provider in ("evon", "openai") or os.getenv("EVON_API_BASE"):
        return EvonOpenAIClient(
            api_base=api_base,
            api_key=api_key,
            model=model,
        )

    if selected_provider == "transformers" or os.getenv("USE_LOCAL_TRANSFORMERS", "").lower() == "true":
        return LocalTransformersLLMClient(model_id=model)

    # High-reliability adaptive reasoning engine with entity extraction & dialogue policy
    return AdaptiveDistressReasoningEngine()
