"""Noisy-channel models of ASR errors: P(spoken | true name).

`ChannelModel.learn` learns confusion matrices from (reference, hypothesis) pairs.
`NaiveChannel` is the uniform-cost Levenshtein baseline.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, List, Optional, Set, Tuple

import numpy as np

ALPHABET = "abcdefghijklmnopqrstuvwxyz "
IDX = {c: i for i, c in enumerate(ALPHABET)}
V = len(ALPHABET)


def clean(text: str) -> str:
    return "".join(c for c in text.lower() if c in IDX)


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _align(true: str, spoken: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
    m, n = len(true), len(spoken)
    d = np.zeros((m + 1, n + 1), dtype=np.int32)
    d[:, 0] = np.arange(m + 1)
    d[0, :] = np.arange(n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            d[i, j] = min(
                d[i - 1, j] + 1,
                d[i, j - 1] + 1,
                d[i - 1, j - 1] + (true[i - 1] != spoken[j - 1]),
            )
    i, j = m, n
    ops: List[Tuple[str, Optional[str], Optional[str]]] = []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + (true[i - 1] != spoken[j - 1]):
            ops.append(("emit", true[i - 1], spoken[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            ops.append(("del", true[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, spoken[j - 1]))
            j -= 1
    return ops


class NaiveChannel:
    """Every edit costs the same. loglik = -lam * edit_distance."""

    def __init__(self, lam: float = 3.0) -> None:
        self.lam = lam

    def loglik(self, spoken: str, name: str) -> float:
        return -self.lam * levenshtein(clean(spoken), clean(name))


class ChannelModel:
    def __init__(self, log_emit: np.ndarray, log_del: np.ndarray, log_ins: np.ndarray) -> None:
        self.le = log_emit.tolist()
        self.ld = log_del.tolist()
        self.li = log_ins.tolist()

    @classmethod
    def learn(
        cls,
        pairs: Iterable[Tuple[str, str]],
        alpha: float = 0.3,
        identity_prior: float = 2.0,
    ) -> ChannelModel:
        emit = np.full((V, V), alpha)
        emit[np.arange(V), np.arange(V)] += identity_prior
        dele = np.full(V, alpha)
        ins = np.full(V, alpha)
        n_true = 0
        for t, s in pairs:
            t, s = clean(t), clean(s)
            n_true += len(t)
            for op, a, b in _align(t, s):
                if op == "emit" and a is not None and b is not None:
                    emit[IDX[a], IDX[b]] += 1
                elif op == "del" and a is not None:
                    dele[IDX[a]] += 1
                elif b is not None:
                    ins[IDX[b]] += 1
        total = emit.sum(1) + dele
        log_emit = np.log(emit / total[:, None])
        log_del = np.log(dele / total)
        q_ins = max((ins.sum() - alpha * V) / max(n_true, 1), 1e-4)
        log_ins = np.log(ins / ins.sum()) + math.log(q_ins)
        return cls(log_emit, log_del, log_ins)

    def loglik(self, spoken: str, name: str) -> float:
        s = [IDX[c] for c in clean(spoken)]
        t = [IDX[c] for c in clean(name)]
        m, n = len(t), len(s)
        le, ld, li = self.le, self.ld, self.li
        neg_inf = -1e18
        prev = [0.0] * (n + 1)
        for j in range(1, n + 1):
            prev[j] = prev[j - 1] + li[s[j - 1]]
        for i in range(1, m + 1):
            ti = t[i - 1]
            cur = [prev[0] + ld[ti]] + [neg_inf] * n
            lei = le[ti]
            for j in range(1, n + 1):
                sj = s[j - 1]
                cur[j] = max(prev[j - 1] + lei[sj], prev[j] + ld[ti], cur[j - 1] + li[sj])
            prev = cur
        return prev[n]


def _bigrams(s: str) -> Set[str]:
    s = f"^{clean(s)}$"
    return {s[i : i + 2] for i in range(len(s) - 1)}


class NameIndex:
    """Candidate-name scoring: bigram prefilter, then channel log-likelihood on top k."""

    def __init__(self, names: list[str], channel: Any, k: int = 25) -> None:
        self.names, self.channel, self.k = names, channel, k
        self.grams = [_bigrams(n) for n in names]
        self._cache: dict[str, np.ndarray] = {}

    def scores(self, spoken: str) -> np.ndarray:
        hit = self._cache.get(spoken)
        if hit is not None:
            return hit
        g = _bigrams(spoken)
        dice = np.array(
            [
                (2 * len(g & gn) / (len(g) + len(gn))) if (len(g) + len(gn)) > 0 else 0.0
                for gn in self.grams
            ]
        )
        out = np.full(len(self.names), -np.inf)
        for i in np.argsort(-dice)[: self.k]:
            out[i] = self.channel.loglik(spoken, self.names[i])
        self._cache[spoken] = out
        return out
