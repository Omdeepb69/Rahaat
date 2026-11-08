"""Unit tests for LLM reasoning and adaptive disaster entity extraction."""
from __future__ import annotations

from typing import Any

import pytest

from raahat.infrastructure.llm.adaptive_engine import AdaptiveDistressReasoningEngine
from raahat.infrastructure.llm.factory import create_llm_client


@pytest.mark.asyncio
async def test_adaptive_extraction_all_facts_in_first_utterance() -> None:
    """Verify that when a caller states location, headcount, and needs at once, the system captures all."""
    engine = AdaptiveDistressReasoningEngine()
    utterance = (
        "Hum Alappuzha Boat Jetty ke pass 5 log chhat par phanse hain, "
        "paani 6 feet badh gaya hai, jaldi rescue boat bhejo!"
    )

    res = await engine.extract_and_respond(
        dialog_history=[],
        current_facts={},
        latest_user_utterance=utterance,
        language_code="hi",
    )

    assert res.location_text is not None
    assert "Alappuzha" in res.location_text
    assert res.people_count == 5
    assert "boat" in res.needs
    assert "water_rising_fast" in res.hazards or "trapped_roof" in res.hazards
    assert res.assessed_priority == "P0"  # Critical due to water rising & trapped roof
    assert res.is_completed is True  # All vital facts captured in turn 1!
    assert "Alappuzha" in res.next_prompt
    assert "5" in res.next_prompt


@pytest.mark.asyncio
async def test_adaptive_extraction_sequential_turns() -> None:
    """Verify that if caller gives location first, the engine asks for missing headcount."""
    engine = AdaptiveDistressReasoningEngine()

    # Turn 1: Only location
    res1 = await engine.extract_and_respond(
        dialog_history=[],
        current_facts={},
        latest_user_utterance="Ernakulam General Hospital ke pass hain hum",
        language_code="hi",
    )
    assert res1.location_text is not None
    assert "Ernakulam" in res1.location_text
    assert res1.people_count is None
    assert res1.is_completed is False
    assert "people_count" in res1.missing_fields
    assert "kitne log" in res1.next_prompt.lower()

    # Turn 2: Headcount provided
    facts_turn2: dict[str, Any] = {
        "location_text": res1.location_text,
        "people_count": None,
        "needs": [],
    }
    res2 = await engine.extract_and_respond(
        dialog_history=[{"role": "caller", "content": "Ernakulam General Hospital ke pass hain hum"}],
        current_facts=facts_turn2,
        latest_user_utterance="Hum 8 log hain",
        language_code="hi",
    )
    assert res2.people_count == 8
    assert res2.is_completed is False
    assert "needs" in res2.missing_fields
    assert "madad" in res2.next_prompt.lower()

    # Turn 3: Needs provided
    facts_turn3: dict[str, Any] = {
        "location_text": res2.location_text,
        "people_count": res2.people_count,
        "needs": [],
    }
    res3 = await engine.extract_and_respond(
        dialog_history=[],
        current_facts=facts_turn3,
        latest_user_utterance="Doctor aur naav chahiye, ek bujurg vyakti bimar hain",
        language_code="hi",
    )
    assert "medical" in res3.needs
    assert "boat" in res3.needs
    assert res3.medical_urgency is True
    assert res3.assessed_priority == "P0"
    assert res3.is_completed is True


@pytest.mark.asyncio
async def test_create_llm_client_factory() -> None:
    """Verify create_llm_client instantiates adaptive engine by default."""
    client = create_llm_client()
    assert isinstance(client, AdaptiveDistressReasoningEngine)
