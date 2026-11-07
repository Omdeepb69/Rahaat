"""Probe on ASR output for landmark recognition."""
from __future__ import annotations

import argparse
import csv
import re
from typing import Any, Dict, List, Tuple

import numpy as np

from .asr_sim import corrupt
from .channel import ChannelModel, NaiveChannel, NameIndex, clean
from .gazetteer import City

TEMPLATE_WORDS = [
    r"\bke paas\b",
    r"\bke samne\b",
    r"\bke peeche\b",
    r"\bke bagal mein\b",
    r"\bhoon\b",
    r"\bwali gali mein\b",
    r"\bpaani bhar gaya hai\b",
    r"\bmain\b",
]


def strip_template(text: str) -> str:
    """Remove common relation phrases so a sentence can be scored as a landmark name."""
    t = text.lower()
    for pat in TEMPLATE_WORDS:
        t = re.sub(pat, " ", t)
    return re.sub(r"\s+", " ", t).strip()


def load_pairs(path: str, strip: bool = False) -> List[Tuple[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        (
            clean(r["reference"]),
            clean(strip_template(r["hypothesis"]) if strip else r["hypothesis"]),
        )
        for r in rows
    ]


def _topk(index: NameIndex, hyp: str, ref: str, names: List[str]) -> Tuple[bool, bool]:
    order = np.argsort(-index.scores(hyp))
    ranked = [names[i] for i in order[:3]]
    return ranked[0] == ref, ref in ranked


def evaluate(pairs: List[Tuple[str, str]], extra_names: List[str]) -> Dict[str, Any]:
    names = sorted({r for r, _ in pairs} | {clean(n) for n in extra_names})
    exact = float(np.mean([r == h for r, h in pairs]))
    naive = NameIndex(names, NaiveChannel())
    n1 = n3 = l1 = l3 = 0
    for fold in (0, 1):
        train = [p for i, p in enumerate(pairs) if i % 2 != fold]
        test = [p for i, p in enumerate(pairs) if i % 2 == fold]
        learned = NameIndex(names, ChannelModel.learn(train))
        for ref, hyp in test:
            a, b = _topk(naive, hyp, ref, names)
            n1, n3 = n1 + a, n3 + b
            a, b = _topk(learned, hyp, ref, names)
            l1, l3 = l1 + a, l3 + b
    n = len(pairs)
    return {
        "n": n,
        "candidates": len(names),
        "exact_match": exact,
        "naive_top1": n1 / n,
        "naive_top3": n3 / n,
        "learned_top1": l1 / n,
        "learned_top3": l3 / n,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument(
        "--names-file",
        help="one landmark name per line (distractors from the real gazetteer)",
    )
    ap.add_argument("--strip-template", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--noise", type=float, default=0.2)
    a = ap.parse_args()

    city = City()
    extra = city.names
    if a.names_file:
        extra = [line.strip() for line in open(a.names_file, encoding="utf-8") if line.strip()]
    if a.selftest or not a.csv:
        rng = np.random.default_rng(0)
        pairs = [(n, corrupt(n, a.noise, rng)) for n in city.names for _ in range(6)]
        print(
            f"[selftest] simulated ASR noise p={a.noise}; this is NOT a measurement of any real ASR"
        )
    else:
        pairs = load_pairs(a.csv, a.strip_template)
    r = evaluate(pairs, extra)
    print(f"utterances={r['n']}  candidate names={r['candidates']}")
    print(f"exact string match      : {r['exact_match']:.0%}")
    print(f"naive matcher  top-1/3  : {r['naive_top1']:.0%} / {r['naive_top3']:.0%}")
    print(f"learned matcher top-1/3 : {r['learned_top1']:.0%} / {r['learned_top3']:.0%}  (2-fold CV)")


if __name__ == "__main__":
    main()
