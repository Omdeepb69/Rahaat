"""Adaptive semantic disaster understanding and dynamic dialogue engine.

Provides zero-latency, deterministic extraction of disaster distress entities,
missing-information analysis, and context-aware next-turn prompt formulation.
Can operate stand-alone or as a high-reliability fallback for LLM APIs.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from .protocol import EmergencyFactExtraction, LLMClient

logger = logging.getLogger(__name__)

# Numeric words across Indian languages and English
NUMERIC_WORDS: dict[str, int] = {
    # Hindi / Hinglish
    "ek": 1,
    "do": 2,
    "teen": 3,
    "chaar": 4,
    "char": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "che": 6,
    "saat": 7,
    "sat": 7,
    "aath": 8,
    "ath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "barah": 12,
    "pandrah": 15,
    "bees": 20,
    "pachees": 25,
    "tees": 30,
    "chalis": 40,
    "pachas": 50,
    # English
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
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    # Malayalam transliterated
    "onnu": 1,
    "rendu": 2,
    "moonu": 3,
    "naalu": 4,
    "anju": 5,
    "aaru": 6,
    "yezhu": 7,
    "ettu": 8,
    "onpathu": 9,
    "pathu": 10,
    # Marathi
    "don": 2,
    "tin": 3,
    "pach": 5,
    "saha": 6,
    "daha": 10,
}

# Known Kerala and Maharashtra landmark indicators
COMMON_LANDMARK_TERMS = [
    "alappuzha",
    "ernakulam",
    "munnar",
    "shakthan",
    "marine drive",
    "chalakudy",
    "pamba",
    "shaniwar wada",
    "bund garden",
    "general hospital",
    "bus stand",
    "boat jetty",
    "river ghat",
    "bridge",
    "station",
    "temple",
    "church",
    "school",
    "college",
    "junction",
    "road",
    "nagar",
    "colony",
]


class AdaptiveDistressReasoningEngine(LLMClient):
    """Reasoning engine for dynamic disaster dialogue and fact extraction.

    Extracts location, people count, hazards, and medical emergencies from caller
    speech. Decides what critical missing information to ask next, avoiding redundant
    questions if the caller already provided information.
    """

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Synthesize natural dialogue text given a prompt."""
        return "Dhanyawad. Aapki suraksha hamari prathmikta hai. Jankari darj ho gayi hai."

    async def extract_and_respond(
        self,
        dialog_history: list[dict[str, str]],
        current_facts: Mapping[str, Any],
        latest_user_utterance: str,
        language_code: str = "hi",
    ) -> EmergencyFactExtraction:
        """Extract updated disaster facts and formulate the next dynamic question."""
        text = latest_user_utterance.strip()
        text_lower = text.lower()

        # 1. Location Extraction
        existing_loc = str(current_facts.get("location_text") or "").strip() or None
        new_loc = self._extract_location(text, existing_loc)
        location_text = new_loc or existing_loc

        # 2. People Count Extraction
        existing_count = current_facts.get("people_count")
        count_val = int(existing_count) if isinstance(existing_count, (int, str)) and str(existing_count).isdigit() else None
        people_count: Optional[int]
        if count_val is not None:
            people_count = count_val
        else:
            people_count = self._extract_people_count(text)

        # 3. Needs & Hazards Extraction
        raw_needs = current_facts.get("needs")
        existing_needs: list[str] = [str(x) for x in raw_needs] if isinstance(raw_needs, list) else []
        new_needs, new_hazards, medical_flag = self._extract_needs_and_hazards(text_lower)

        combined_needs = list(dict.fromkeys(existing_needs + new_needs))
        raw_hazards = current_facts.get("hazards")
        existing_hazards: list[str] = [str(x) for x in raw_hazards] if isinstance(raw_hazards, list) else []
        combined_hazards = list(dict.fromkeys(existing_hazards + new_hazards))
        is_medical = bool(current_facts.get("medical_urgency") or medical_flag)

        # 4. Priority Assessment (P0 Critical, P1 High, P2 Moderate)
        priority = "P1"
        if is_medical or (people_count and people_count >= 10) or any(
            h in ("water_rising_fast", "trapped_roof", "submerged", "drowning_risk") for h in combined_hazards
        ):
            priority = "P0"
        elif "boat" in combined_needs or "evacuation" in combined_needs:
            priority = "P1"
        elif combined_needs:
            priority = "P2"

        # 5. Situation Summary
        loc_str = location_text or "undetermined location"
        count_str = f"{people_count} individuals" if people_count else "uncounted victims"
        hazard_str = f" facing {', '.join(combined_hazards)}" if combined_hazards else ""
        need_str = f" requiring {', '.join(combined_needs)}" if combined_needs else ""
        situation_summary = (
            f"Emergency reported at {loc_str}: {count_str}{hazard_str}{need_str}. Assessed as {priority}."
        )

        # 6. Determine Missing Fields & Dynamic Next Question
        missing_fields: list[str] = []
        if not location_text:
            missing_fields.append("location")
        if people_count is None:
            missing_fields.append("people_count")
        if not combined_needs:
            missing_fields.append("needs")

        is_completed = False
        next_prompt = ""

        # Formulate dynamic response based on what is known vs missing
        if not location_text and people_count is None:
            next_prompt = "Aap kahan phanse hain aur aapke saath kitne log hain? Kripya sthan aur sankhya batayein."
        elif not location_text:
            if people_count:
                next_prompt = (
                    f"Samajh gaya, {people_count} log hain. Kripya apna sthan ya aas-paas ka landmark batayein?"
                )
            else:
                next_prompt = "Kripya apna sthan ya aas-paas ka landmark batayein."
        elif people_count is None:
            next_prompt = (
                f"{location_text} note kar liya hai. Aapke saath wahan kitne log hain? Kripya sankhya batayein."
            )
        elif not combined_needs:
            next_prompt = (
                f"{people_count} log darj hue. Kis tarah ki madad chahiye? Jaise ki naav, doctor, ya bhojan?"
            )
        else:
            # All vital disaster facts gathered! Wrap up immediately to initiate rescue dispatch.
            is_completed = True
            resource_ref = "Rescue team aur naav" if "boat" in combined_needs else "Aapatkalin bachav dal"
            next_prompt = (
                f"Jankari darj ho gayi hai: {location_text} par {people_count} logon ke liye. "
                f"{resource_ref} ko turant rawana kiya ja raha hai. Kripya oonche sthan par rahein, madad pahunch rahi hai!"
            )

        return EmergencyFactExtraction(
            location_text=location_text,
            people_count=people_count,
            needs=combined_needs,
            hazards=combined_hazards,
            medical_urgency=is_medical,
            assessed_priority=priority,
            situation_summary=situation_summary,
            next_prompt=next_prompt,
            is_completed=is_completed,
            missing_fields=missing_fields,
        )

    def _extract_location(self, text: str, existing_loc: Optional[str]) -> Optional[str]:
        """Extract geographic landmark or location mention."""
        text_clean = text.strip()
        text_lower = text_clean.lower()

        # If previous confirmed location exists, preserve it
        if existing_loc:
            return existing_loc

        # If utterance is a concise location phrase (1-8 words) without other actions
        words = text_clean.split()
        if 1 <= len(words) <= 8 and not any(w.lower() in ("boat", "doctor", "naav", "dawa") for w in words):
            ignore = {"haan", "nahi", "theek", "yes", "no", "ok", "help", "bachao", "madad"}
            if not all(w.lower() in ignore for w in words):
                return text_clean

        # Check known landmark vocabulary
        for lm in COMMON_LANDMARK_TERMS:
            if lm in text_lower:
                idx = text_lower.find(lm)
                # Capture phrase up to 40 characters around landmark
                start = max(0, text_clean.rfind(" ", 0, idx) + 1 if text_clean.rfind(" ", 0, idx) != -1 else 0)
                end = min(len(text_clean), idx + len(lm) + 20)
                candidate = text_clean[start:end].strip(" .,!?")
                candidate = re.sub(r"\b(ke pass|ke paas|mein|me|near|at|par)\b", "", candidate, flags=re.IGNORECASE).strip()
                if candidate:
                    return candidate.title()
                return lm.title()

        # Extract prepositional phrases ("... ke pass", "... ke paas", "near ...", "at ...")
        prep_patterns = [
            r"(?:near|at)\s+([A-Za-z0-9\s]{3,35})(?:,|\.|$)",
            r"([A-Za-z0-9\u0900-\u097F\s]{3,35})\s+(?:ke\s+paas|ke\s+pass|me\s+phanse|mein)",
        ]
        for pat in prep_patterns:
            m = re.search(pat, text_clean, re.IGNORECASE)
            if m:
                loc = m.group(1).strip()
                if len(loc.split()) <= 6 and not any(loc.lower() == w for w in ["hum", "we", "log", "madad"]):
                    return loc.title()

        return None

    def _extract_people_count(self, text: str) -> Optional[int]:
        """Extract trapped headcount from numerals or words."""
        # Strip measurements and temporal markers (e.g. 5 feet, 2nd floor, 3 hours)
        cleaned = re.sub(
            r"\b\d+\s*(?:feet|foot|ft|inch|meter|mtr|floor|manzil|ghante|hours|baje|pm|am)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # Strip location numbers (e.g. Ward 5, Sector 4, Room 12, Flat 3, Lane 2, Gate 1, Block A4)
        cleaned = re.sub(
            r"\b(?:ward|sector|room|flat|plot|lane|gate|gali|block|pin|pincode|no|number)\s*\d+\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        # Check digit patterns with explicit headcount indicator (e.g. "4 log", "5 people", "4 vyakti")
        explicit_match = re.search(
            r"\b(\d{1,4})\s*(?:log|people|person|vyakti|members|jan|adults|bacche)\b",
            cleaned,
            re.IGNORECASE,
        )
        if explicit_match:
            try:
                count = int(explicit_match.group(1))
                if 1 <= count <= 5000:
                    return count
            except ValueError:
                pass

        # Check word-based numbers (e.g. "chaar", "four", "panch")
        tokens = re.findall(r"\b[a-zA-Z\u0900-\u097F]+\b", cleaned.lower())
        for token in tokens:
            if token in NUMERIC_WORDS:
                return NUMERIC_WORDS[token]

        # Standalone digits if utterance is short (e.g. "4" or "4.")
        standalone = re.search(r"\b(\d{1,4})\b", cleaned)
        if standalone:
            try:
                count = int(standalone.group(1))
                if 1 <= count <= 5000:
                    return count
            except ValueError:
                pass

        return None

    def _extract_needs_and_hazards(
        self, text_lower: str
    ) -> tuple[list[str], list[str], bool]:
        """Extract requested relief needs, environmental hazards, and medical urgency."""
        needs: list[str] = []
        hazards: list[str] = []
        medical_flag = False

        # Needs
        if any(w in text_lower for w in ["naav", "boat", "motorboat", "dinghy", "evacuate", "evacuation"]):
            needs.append("boat")
        if any(w in text_lower for w in ["doctor", "medical", "dawa", "medicine", "ambulance", "hospital", "injur"]):
            needs.append("medical")
            medical_flag = True
        if any(w in text_lower for w in ["khana", "food", "paani", "water", "drinking water", "ration"]):
            needs.append("food_water")
        if any(w in text_lower for w in ["shelter", "raahat shivir", "tents", "camp"]):
            needs.append("shelter")

        # Hazards
        if any(w in text_lower for w in ["paani badh", "water rising", "water level", "feet", "chest deep", "submerg"]):
            hazards.append("water_rising_fast")
        if any(w in text_lower for w in ["chhat", "roof", "rooftop", "terrace", "upar phanse"]):
            hazards.append("trapped_roof")
        if any(w in text_lower for w in ["current", "tez bahaav", "flow", "sweep"]):
            hazards.append("strong_current")
        if any(w in text_lower for w in ["collapsed", "gir gaya", "tuta", "building", "wall"]):
            hazards.append("structural_collapse")
        if any(w in text_lower for w in ["elderly", "bujurg", "pregnant", "garbhwati", "bachha", "child", "infant", "oxygen"]):
            hazards.append("vulnerable_individuals")
            medical_flag = True

        return needs, hazards, medical_flag
