"""Number read-back generation and confirmation helpers."""
from __future__ import annotations

import re
from typing import Optional

HINDI_NUMBER_WORDS = {
    "ek": 1,
    "do": 2,
    "teen": 3,
    "chaar": 4,
    "paanch": 5,
    "chhah": 6,
    "chhe": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "barah": 12,
    "pandrah": 15,
    "bees": 20,
    "pachees": 25,
    "tees": 30,
    "pachaas": 50,
}

ENGLISH_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "twenty-five": 25,
    "thirty": 30,
    "fifty": 50,
}


def extract_people_count_from_text(text: str) -> Optional[int]:
    """Extract integer count of people from spoken or transcribed text."""
    clean = text.lower().strip()

    # 1. Match explicit digits (e.g., "4 people", "we are 5", "3")
    digit_match = re.search(r"\b(\d{1,3})\b", clean)
    if digit_match:
        val = int(digit_match.group(1))
        if 1 <= val <= 500:
            return val

    # 2. Match number words
    for word, num in {**HINDI_NUMBER_WORDS, **ENGLISH_NUMBER_WORDS}.items():
        if re.search(rf"\b{word}\b", clean):
            return num

    return None


def generate_number_readback_prompt(count: int, language: str = "hi") -> str:
    """Generate prompt to read back and confirm an extracted headcount."""
    if language == "en":
        return (
            f"You reported {count} people. "
            f"Press 1 or say Yes to confirm. Press 2 or say No to correct."
        )
    return (
        f"Aapne bataya {count} vyakti. "
        f"Pushti ke liye 1 dabayein ya Haan bolein. "
        f"Sankhya badalne ke liye 2 dabayein ya Nahi bolein."
    )


def evaluate_readback_confirmation(
    dtmf_digits: Optional[str] = None,
    spoken_text: Optional[str] = None,
) -> Optional[bool]:
    """Determine whether caller confirmed or rejected the read-back number.

    Returns:
        True: Confirmed (DTMF 1 or affirmative words)
        False: Rejected (DTMF 2 or negative words)
        None: Ambiguous / not recognized
    """
    if dtmf_digits:
        digits = dtmf_digits.strip()
        if digits == "1":
            return True
        if digits == "2":
            return False

    if spoken_text:
        text = spoken_text.lower().strip()
        affirmative_words = {"haan", "yes", "sahi", "theek", "correct", "confirm", "ji haan"}
        negative_words = {"nahi", "no", "galat", "wrong", "nahi hai", "change", "badlo"}

        for aff in affirmative_words:
            if re.search(rf"\b{aff}\b", text):
                return True

        for neg in negative_words:
            if re.search(rf"\b{neg}\b", text):
                return False

    return None
