"""LLM and reasoning protocol definitions for disaster distress understanding."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable


@dataclass
class LLMMessage:
    """A single chat message in an LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class EmergencyFactExtraction:
    """Structured disaster facts extracted dynamically from caller dialogue."""

    location_text: Optional[str] = None
    people_count: Optional[int] = None
    needs: list[str] = field(default_factory=list)
    hazards: list[str] = field(default_factory=list)
    medical_urgency: bool = False
    assessed_priority: str = "P1"  # "P0", "P1", "P2", "P3"
    situation_summary: str = ""
    next_prompt: str = ""
    is_completed: bool = False
    missing_fields: list[str] = field(default_factory=list)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM reasoning backends (Evon, local transformer, or reasoning engine)."""

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Generate text completion from prompt."""
        ...

    async def extract_and_respond(
        self,
        dialog_history: list[dict[str, str]],
        current_facts: Mapping[str, Any],
        latest_user_utterance: str,
        language_code: str = "hi",
    ) -> EmergencyFactExtraction:
        """Extract updated disaster facts and formulate the next dynamic question."""
        ...
