"""Transliteration normalization and synonym expansion for landmark matching."""
from __future__ import annotations

import re

SYNONYM_PAIRS = [
    ("mandir", "temple"),
    ("vidyalaya", "school"),
    ("shala", "school"),
    ("aspatal", "hospital"),
    ("dawakhana", "clinic"),
    ("pul", "bridge"),
    ("pool", "bridge"),
    ("masjid", "mosque"),
    ("mandi", "market"),
    ("bazar", "market"),
    ("bazaar", "market"),
    ("talab", "lake"),
    ("talaab", "lake"),
    ("chowk", "square"),
    ("chawk", "chowk"),
    ("chauk", "chowk"),
    ("marg", "road"),
    ("rasta", "road"),
]


def normalize_transliteration(text: str) -> str:
    """Normalize common Hindi/Indic Romanized transliteration variations."""
    clean = text.lower().strip()
    # Strip punctuation
    clean = re.sub(r"[^\w\s]", " ", clean)

    # Normalize double vowels and common transliteration digraphs
    clean = re.sub(r"aa+", "a", clean)
    clean = re.sub(r"ee+", "i", clean)
    clean = re.sub(r"oo+", "u", clean)
    clean = re.sub(r"\bph", "f", clean)
    clean = re.sub(r"\bw", "v", clean)

    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def generate_query_variants(text: str) -> list[str]:
    """Generate search variants for a spoken or transcribed landmark description."""
    raw = text.lower().strip()
    norm = normalize_transliteration(raw)

    variants: list[str] = []
    for candidate in [raw, norm]:
        if candidate and candidate not in variants:
            variants.append(candidate)

    # Apply synonym substitutions
    for var in list(variants):
        for term1, term2 in SYNONYM_PAIRS:
            if re.search(rf"\b{term1}\b", var):
                substituted = re.sub(rf"\b{term1}\b", term2, var)
                if substituted not in variants:
                    variants.append(substituted)
            elif re.search(rf"\b{term2}\b", var):
                substituted = re.sub(rf"\b{term2}\b", term1, var)
                if substituted not in variants:
                    variants.append(substituted)

    return variants

