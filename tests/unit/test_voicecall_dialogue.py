from raahat.application.voicecall import dialogue, script


def test_questions_already_answered_are_skipped() -> None:
    facts = dialogue.Facts()
    outcome = dialogue.answer(facts, "situation", "Water entered our house, 6 people trapped near the railway station")
    assert facts.people_count == 6 and facts.trapped
    assert facts.place
    assert outcome.step == "callback"


def test_people_answer_can_be_a_bare_number() -> None:
    facts = dialogue.Facts()
    dialogue.answer(facts, "situation", "flood")
    dialogue.answer(facts, "location", "Kalady")
    assert dialogue.answer(facts, "people", "7").step == "safety"
    assert facts.people_count == 7


def test_phone_numbers_with_gaps_and_prefixes() -> None:
    assert dialogue.find_phone("+91 98765-43210") == "9876543210"
    assert dialogue.find_phone("call 09876543210") == "9876543210"
    assert dialogue.find_phone("12345") is None


def test_name_can_be_skipped() -> None:
    facts = dialogue.Facts()
    dialogue.answer(facts, "name", "no")
    assert facts.name is None


def test_language_from_script_and_fallback() -> None:
    assert script.language_of_text("വെള്ളം കയറി") == "ml"
    assert script.language_of_text("पानी भर गया") == "hi"
    assert script.language_of_text("water is rising") == "en"
    assert script.supported("or-IN") == "hi"
    assert script.supported("ml-IN") == "ml"


def test_every_language_has_every_prompt() -> None:
    for language in script.SUPPORTED:
        for key in (*script.STEPS, "done", "retry"):
            line = script.line(language, key)
            assert line.text and "112" not in line.spoken
