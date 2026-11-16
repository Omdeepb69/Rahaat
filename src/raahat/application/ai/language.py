"""Language identification for typed text.

For audio the speech provider reports the language. For text this module uses
the writing system and a small function-word lexicon. It is a heuristic with
known limits, and reports them:

* Malayalam script identifies Malayalam unambiguously.
* Devanagari is shared by Hindi, Konkani and Marathi. They are separated by
  common function words; when none are present the result is ``hi`` with the
  alternatives listed and ``certain=False``.
* Latin script may be English or a romanised Indian language; short messages
  are frequently ambiguous.

No numeric confidence is produced because none has been calibrated.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SUPPORTED_LANGUAGES = {
    "ml": "Malayalam",
    "en": "English",
    "hi": "Hindi",
    "kok": "Konkani",
}

_DEVANAGARI_MARKERS: dict[str, frozenset[str]] = {
    "hi": frozenset(
        "है हैं नहीं और में हम मुझे यहाँ यहां पानी हमारे कृपया रहा रही रहे गया गई था थी को से".split()
    ),
    "kok": frozenset(
        "आसा आसात ना हांव आमी आमकां तुमी म्हजें खंय कितें उदक लागीं जाय आनी घरांत मजत".split()
    ),
    "mr": frozenset("आहे आहेत नाही आणि आम्ही मला तुम्ही आमच्या पाणी झाले येथे".split()),
}

_LATIN_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset(
        "the is are we and water help near house people need please there our has have with".split()
    ),
    "hi": frozenset(
        "hai hain nahi nahin paani pani hum mein bachao madad yahan ghar log aur humara kripya raha".split()
    ),
    "kok": frozenset("asa asat amkam amchem udok zai hanv khoim kitem lagim mozot ghorant".split()),
    "ml": frozenset(
        "vellam njan njangal undu illa sahayam veedu veettil aanu ivide venam rakshikkanam".split()
    ),
}

# Split on whitespace and punctuation only: combining vowel signs are part of a word.
_WORD = re.compile(r"[^\s\d,.;:!?।\"'()\[\]{}\-–—/\\]+")


@dataclass(frozen=True)
class LanguageGuess:
    language: str  # ISO 639 code, or "und" when undetermined
    certain: bool
    basis: str
    alternatives: tuple[str, ...] = ()


def _script_counts(text: str) -> dict[str, int]:
    counts = {"malayalam": 0, "devanagari": 0, "latin": 0, "other": 0}
    for ch in text:
        if not ch.isalpha():
            continue
        code = ord(ch)
        if 0x0D00 <= code <= 0x0D7F:
            counts["malayalam"] += 1
        elif 0x0900 <= code <= 0x097F:
            counts["devanagari"] += 1
        elif "LATIN" in unicodedata.name(ch, ""):
            counts["latin"] += 1
        else:
            counts["other"] += 1
    return counts


def _score(words: list[str], markers: dict[str, frozenset[str]]) -> dict[str, int]:
    return {lang: sum(1 for w in words if w in vocab) for lang, vocab in markers.items()}


def identify_language(text: str) -> LanguageGuess:
    stripped = text.strip()
    if not stripped:
        return LanguageGuess("und", False, "empty text")
    counts = _script_counts(stripped)
    letters = sum(counts.values())
    if letters == 0:
        return LanguageGuess("und", False, "no alphabetic characters")
    dominant = max(counts, key=lambda k: counts[k])
    words = [w.lower() for w in _WORD.findall(stripped)]

    if dominant == "malayalam":
        mixed = counts["latin"] > 0
        return LanguageGuess(
            "ml",
            True,
            "Malayalam script" + (" with Latin-script words" if mixed else ""),
        )

    if dominant == "devanagari":
        scores = _score(words, _DEVANAGARI_MARKERS)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_hits = ranked[0]
        runner_hits = ranked[1][1]
        if best_hits == 0:
            return LanguageGuess(
                "hi",
                False,
                "Devanagari script; no distinguishing words found",
                alternatives=("kok", "mr"),
            )
        if best_hits == runner_hits:
            tied = tuple(lang for lang, hits in ranked if hits == best_hits)
            return LanguageGuess(
                tied[0],
                False,
                "Devanagari script; function words match more than one language",
                alternatives=tied[1:],
            )
        return LanguageGuess(
            best,
            best_hits >= 2 and runner_hits == 0,
            f"Devanagari script; {best_hits} {SUPPORTED_LANGUAGES.get(best, best)} function word(s)",
            alternatives=tuple(lang for lang, hits in ranked[1:] if hits > 0),
        )

    if dominant == "latin":
        scores = _score(words, _LATIN_MARKERS)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_hits = ranked[0]
        runner_hits = ranked[1][1]
        if best_hits == 0:
            return LanguageGuess("und", False, "Latin script; no known words found")
        if best_hits == runner_hits:
            tied = tuple(lang for lang, hits in ranked if hits == best_hits)
            return LanguageGuess(
                tied[0],
                False,
                "Latin script; words match more than one language",
                alternatives=tied[1:],
            )
        romanised = "" if best == "en" else " (romanised)"
        return LanguageGuess(
            best,
            best_hits >= 3 and runner_hits == 0,
            f"Latin script; {best_hits} known word(s){romanised}",
            alternatives=tuple(lang for lang, hits in ranked[1:] if hits > 0),
        )

    return LanguageGuess("und", False, "unsupported script")
