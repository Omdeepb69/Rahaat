"""Synthetic ASR noise model. Stands in for real ASR output in simulations."""
from __future__ import annotations

import numpy as np

ALPHABET = "abcdefghijklmnopqrstuvwxyz"
VOWELS = "aeiou"
CONFUSABLE = {
    "a": "eo",
    "e": "ai",
    "i": "ey",
    "o": "ua",
    "u": "o",
    "v": "wb",
    "w": "v",
    "b": "vp",
    "d": "tj",
    "t": "dh",
    "k": "gc",
    "g": "kj",
    "s": "zc",
    "z": "sj",
    "p": "bf",
    "c": "ks",
    "j": "zg",
    "n": "m",
    "m": "n",
    "y": "i",
    "r": "l",
    "l": "r",
    "f": "p",
    "h": "k",
}


def corrupt(text: str, p: float, rng: np.random.Generator) -> str:
    """Per-character substitution / deletion / insertion with probability p."""
    out: list[str] = []
    for ch in text:
        if ch == " ":
            if rng.random() < p * 0.5:
                continue
            out.append(ch)
            continue
        if rng.random() >= p:
            out.append(ch)
            continue
        r = rng.random()
        if r < 0.55:
            cands = CONFUSABLE.get(ch, "")
            if cands and rng.random() < 0.75:
                out.append(cands[int(rng.integers(len(cands)))])
            else:
                out.append(ALPHABET[int(rng.integers(26))])
        elif r < 0.85:
            continue
        else:
            out.append(ch)
            out.append((VOWELS + "h")[int(rng.integers(6))])
    return "".join(out)

