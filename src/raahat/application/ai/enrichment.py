"""Model-assisted translation and structured extraction.

Built on any client that implements ``complete_json``. The model is asked for
a constrained JSON object; the reply is validated field by field and anything
outside the schema is discarded. Every extracted value must be accompanied by
the quote from the report that supports it, and a value whose quote does not
occur in the report text is rejected, which removes the most common form of
fabrication.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from raahat.infrastructure.providers.base import ProviderError
from raahat.infrastructure.providers.llm import JsonModelClient

LANGUAGE_NAMES = {"ml": "Malayalam", "hi": "Hindi", "kok": "Konkani", "en": "English", "mr": "Marathi"}

_TRANSLATE_SYSTEM = (
    "You translate emergency reports into English for a disaster control room. "
    "Translate faithfully and completely. Do not add, infer, summarise or omit anything. "
    "Keep names of people and places as written, transliterated into Latin script. "
    "If part of the text is unintelligible, write [unclear] in its place. "
    'Reply with one JSON object: {"translation": string, "source_language": ISO 639 code}.'
)

_EXTRACT_SYSTEM = (
    "You extract facts from one emergency report for a disaster control room. "
    "Use only what the report states. If the report does not state something, use null. "
    "Never guess numbers, places or conditions. "
    "Reply with one JSON object with exactly these keys:\n"
    '  "category": one of flood, landslide, cyclone, medical, fire, building_collapse, '
    "infrastructure, stranded, other, or null\n"
    '  "people_count": integer or null (people at the location)\n'
    '  "trapped": true or null (true only if the report says people cannot leave)\n'
    '  "medical_emergency": true or null\n'
    '  "life_threatening_medical": true or null\n'
    '  "vulnerable": array from [elderly, children, pregnant, disabled]\n'
    '  "water_level_trend": rising, falling, stable, or null\n'
    '  "water_depth_cm": number or null\n'
    '  "hazards": array from [electrical, landslide, fire, structural_collapse, gas_leak, '
    "strong_current, road_blocked]\n"
    '  "needs": array from [rescue_boat, evacuation, medical, food_water, shelter]\n'
    '  "location_phrases": array of place descriptions exactly as the report words them\n'
    '  "summary": one sentence in English, at most 25 words, stating only reported facts\n'
    '  "quotes": object mapping each non-null key above to the exact words from the report '
    "that support it\n"
    "Use true only for things the report affirms; use null, never false, for anything else."
)

_CATEGORIES = frozenset(
    {"flood", "landslide", "cyclone", "medical", "fire", "building_collapse", "infrastructure",
     "stranded", "other"}
)
_VULNERABLE = frozenset({"elderly", "children", "pregnant", "disabled"})
_HAZARDS = frozenset(
    {"electrical", "landslide", "fire", "structural_collapse", "gas_leak", "strong_current", "road_blocked"}
)
_NEEDS = frozenset({"rescue_boat", "evacuation", "medical", "food_water", "shelter"})
_TRENDS = frozenset({"rising", "falling", "stable"})


@dataclass(frozen=True)
class Translation:
    text: str
    source_language: Optional[str]
    provider: str
    model: str
    duration_ms: float


@dataclass(frozen=True)
class ModelFinding:
    attribute: str
    value: Any
    quote: Optional[str]


@dataclass
class ModelExtraction:
    findings: list[ModelFinding] = field(default_factory=list)
    category: Optional[str] = None
    summary: Optional[str] = None
    location_phrases: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0


def translate_to_english(
    client: JsonModelClient, *, text: str, source_language: Optional[str]
) -> Translation:
    hint = LANGUAGE_NAMES.get(source_language or "", "")
    user = (f"Source language (may be mixed): {hint}\n\n" if hint else "") + f"Report:\n{text}"
    completion = client.complete_json(system=_TRANSLATE_SYSTEM, user=user, max_tokens=2048)
    translation = completion.data.get("translation")
    if not isinstance(translation, str) or not translation.strip():
        raise ProviderError(completion.provider, "translation missing from model reply")
    reported = completion.data.get("source_language")
    return Translation(
        text=translation.strip(),
        source_language=str(reported)[:16] if isinstance(reported, str) and reported else None,
        provider=completion.provider,
        model=completion.model,
        duration_ms=completion.duration_ms,
    )


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def extract_with_model(
    client: JsonModelClient, *, text: str, translated_text: Optional[str] = None
) -> ModelExtraction:
    """Ask the model for structured facts and keep only those grounded in the report."""
    source = text if not translated_text else f"{text}\n\nEnglish translation:\n{translated_text}"
    completion = client.complete_json(
        system=_EXTRACT_SYSTEM, user=f"Report:\n{source}", max_tokens=1536
    )
    data = completion.data
    quotes = data.get("quotes") if isinstance(data.get("quotes"), dict) else {}
    haystack = _normalise(source)
    result = ModelExtraction(
        provider=completion.provider, model=completion.model, duration_ms=completion.duration_ms
    )

    def grounded(key: str) -> Optional[str]:
        """Return the supporting quote if it really occurs in the report."""
        quote = quotes.get(key)
        if isinstance(quote, list):
            quote = next((q for q in quote if isinstance(q, str)), None)
        if not isinstance(quote, str) or len(quote.strip()) < 2:
            return None
        return quote.strip() if _normalise(quote) in haystack else None

    def accept(key: str, attribute: str, value: Any) -> None:
        quote = grounded(key)
        if quote is None:
            result.rejected.append(f"{key}: no supporting quote found in the report")
            return
        result.findings.append(ModelFinding(attribute, value, quote))

    category = data.get("category")
    if isinstance(category, str) and category in _CATEGORIES:
        result.category = category

    people = data.get("people_count")
    if isinstance(people, int) and not isinstance(people, bool) and 0 < people <= 5000:
        accept("people_count", "people_count", people)

    if data.get("trapped") is True:
        accept("trapped", "trapped_status", True)
    if data.get("medical_emergency") is True:
        accept("medical_emergency", "medical_emergency", True)
    if data.get("life_threatening_medical") is True:
        accept("life_threatening_medical", "life_threatening_medical", True)

    trend = data.get("water_level_trend")
    if isinstance(trend, str) and trend in _TRENDS:
        accept("water_level_trend", "water_level_trend", trend)

    depth = data.get("water_depth_cm")
    if isinstance(depth, (int, float)) and not isinstance(depth, bool) and 0 < depth <= 2000:
        accept("water_depth_cm", "water_depth_cm", float(depth))

    for key, attribute, allowed in (
        ("vulnerable", "vulnerable_persons", _VULNERABLE),
        ("hazards", "hazard", _HAZARDS),
        ("needs", "relief_need", _NEEDS),
    ):
        values = data.get(key)
        if not isinstance(values, list):
            continue
        quote = grounded(key)
        for value in values:
            if isinstance(value, str) and value in allowed:
                if quote is None:
                    result.rejected.append(f"{key}={value}: no supporting quote found in the report")
                else:
                    result.findings.append(ModelFinding(attribute, value, quote))

    phrases = data.get("location_phrases")
    if isinstance(phrases, list):
        for phrase in phrases:
            if isinstance(phrase, str) and 3 <= len(phrase.strip()) <= 120:
                if _normalise(phrase) in haystack:
                    result.location_phrases.append(phrase.strip())
                else:
                    result.rejected.append(f"location phrase not in report: {phrase[:60]}")

    summary = data.get("summary")
    if isinstance(summary, str) and summary.strip():
        result.summary = summary.strip()[:400]
    return result
