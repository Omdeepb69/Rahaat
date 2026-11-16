from __future__ import annotations

import pytest

from raahat.application.ai import rules
from raahat.application.ai.language import identify_language


@pytest.mark.parametrize(
    "text,language,certain",
    [
        ("ഞങ്ങൾ വീട്ടിൽ കുടുങ്ങി", "ml", True),
        ("हम 5 लोग छत पर फंसे हैं, पानी बढ़ रहा है", "hi", True),
        ("आमकां मजत जाय, घरांत उदक आसा", "kok", True),
        ("Water is rising near the school, we need help", "en", True),
        ("hum log phanse hain paani badh raha hai", "hi", True),
        ("मदद", "hi", False),
        ("12345", "und", False),
    ],
)
def test_language_identification(text, language, certain):
    guess = identify_language(text)
    assert guess.language == language
    assert guess.certain is certain


def _values(result: rules.RuleExtraction) -> dict[str, list]:
    out: dict[str, list] = {}
    for finding in result.findings:
        out.setdefault(finding.attribute, []).append(finding.value)
    return out


def test_english_extraction_with_quotes():
    result = rules.extract(
        "Water has entered our house behind the school. We are 6 people, two children, "
        "grandmother is bedridden. Water is rising fast."
    )
    values = _values(result)
    assert values["people_count"] == [6]
    assert values["water_level_trend"] == ["rising"]
    assert set(values["vulnerable_persons"]) == {"children", "elderly"}
    assert values["water_entering_occupied_floor"] == [True]
    assert result.category == "flood"
    count = next(f for f in result.findings if f.attribute == "people_count")
    assert count.matched_text == "6 people"
    assert ("behind", "school") in [(m.relation, m.phrase) for m in result.location_mentions]


def test_negation_leaves_facts_unknown():
    result = rules.extract("Nobody is trapped and there are no injuries.")
    values = _values(result)
    assert "trapped_status" not in values
    assert "medical_emergency" not in values


def test_malayalam_and_hindi_extraction():
    ml = _values(rules.extract("ഞങ്ങൾ നാല് പേർ വീട്ടിൽ കുടുങ്ങി, വെള്ളം കയറുന്നു"))
    assert ml["people_count"] == [4] and ml["trapped_status"] == [True] and ml["water_level_trend"] == ["rising"]
    hi = _values(rules.extract("हम 5 लोग छत पर फंसे हैं, पानी बढ़ रहा है"))
    assert hi["people_count"] == [5] and hi["current_floor"] == ["roof"]


def test_depth_requires_water_context_and_converts_units():
    assert "water_depth_cm" not in _values(rules.extract("The house is 4 feet from the road"))
    assert _values(rules.extract("Water is 3 feet deep inside"))["water_depth_cm"] == [91.4]
    body = next(f for f in rules.extract("water is waist deep").findings if f.attribute == "water_depth_cm")
    assert body.note and "approximate" in body.note


def test_no_location_is_invented():
    assert rules.extract("Please help us quickly").location_mentions == []
