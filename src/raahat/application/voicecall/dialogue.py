"""The interview: which question comes next, given what the caller has said.

Each answer is kept verbatim. The same deterministic rules used on every
report pick out facts (people count, someone trapped or hurt, a place, a phone
number) so questions already answered are skipped. Nothing is inferred beyond
what the rules find, and an unclear answer is simply kept as said.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from raahat.application.ai import rules

from .script import STEPS

DONE = "done"
MAX_REPEATS = 1

_DIGIT_GAPS = re.compile(r"(?<=\d)[\s\-.]+(?=\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?91|0)?([6-9]\d{9})(?!\d)")
_FIRST_NUMBER = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")
_SKIP_NAME = re.compile(r"^\s*(no|skip|nahi|nahin|नहीं|नही|വേണ്ട|ഇല്ല|-)\s*[.!।]?\s*$", re.IGNORECASE)


def find_phone(text: str) -> Optional[str]:
    match = _PHONE.search(_DIGIT_GAPS.sub("", text))
    return match.group(1) if match else None


@dataclass
class Facts:
    """What the interview has established so far. Stored as the call's slots."""

    answers: dict[str, str] = field(default_factory=dict)
    repeats: dict[str, int] = field(default_factory=dict)
    people_count: Optional[int] = None
    trapped: bool = False
    medical: bool = False
    place: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None

    @classmethod
    def load(cls, data: dict[str, Any]) -> "Facts":
        known = {k: copy.deepcopy(data[k]) for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def dump(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def absorb(self, text: str) -> None:
        """Take every fact the rules find in ``text``, keeping earlier ones."""
        found = rules.extract(text)
        if self.people_count is None:
            counts = found.values("people_count")
            if counts:
                self.people_count = int(counts[0])
        if found.values("trapped_status"):
            self.trapped = True
        if found.values("medical_emergency") or found.values("life_threatening_medical"):
            self.medical = True
        if self.place is None and found.location_mentions:
            self.place = found.location_mentions[0].phrase
        if self.phone is None:
            self.phone = find_phone(text)

    def is_answered(self, step: str) -> bool:
        if step in self.answers:
            return True
        if step == "location":
            return self.place is not None
        if step == "people":
            return self.people_count is not None
        if step == "safety":
            return self.trapped or self.medical
        if step == "callback":
            return self.phone is not None
        return False


def next_step(facts: Facts) -> str:
    for step in STEPS:
        if not facts.is_answered(step):
            return step
    return DONE


@dataclass(frozen=True)
class Outcome:
    step: str  # the step now being asked, or DONE
    repeat: bool  # the same question is asked again because nothing was heard


def answer(facts: Facts, step: str, text: str) -> Outcome:
    """Record the caller's answer to ``step`` and decide what to ask next."""
    text = (text or "").strip()
    if not text:
        heard = facts.repeats.get(step, 0)
        if heard < MAX_REPEATS:
            facts.repeats[step] = heard + 1
            return Outcome(step, True)
        facts.answers[step] = ""
        return Outcome(next_step(facts), False)

    facts.answers[step] = text
    facts.absorb(text)
    if step == "people" and facts.people_count is None:
        number = _FIRST_NUMBER.search(text)
        if number and 0 < int(number.group(1)) <= 5000:
            facts.people_count = int(number.group(1))
    if step == "location" and facts.place is None:
        facts.place = text[:255]
    if step == "name" and not _SKIP_NAME.match(text) and find_phone(text) is None:
        facts.name = text[:120]
    return Outcome(next_step(facts), False)


PERSONAL_STEPS = frozenset({"callback", "name"})


def narrative(facts: Facts) -> str:
    """The caller's answers in order, as one text for analysis.

    The phone number and name are left out: they travel in the report's
    caller fields, which only roles allowed to see caller details can read.
    """
    return "\n".join(
        facts.answers[s] for s in STEPS if s not in PERSONAL_STEPS and facts.answers.get(s)
    )
