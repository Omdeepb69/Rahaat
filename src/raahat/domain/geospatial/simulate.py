"""Synthetic callers and episode runner for geospatial belief simulation."""
from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple

import numpy as np

from .asr_sim import corrupt
from .engine import WINDOW_R, LocationEngine
from .gazetteer import SIGMA
from .likelihood import C0, P_KNOWS_WARD, P_YES_COVER


class Caller:
    def __init__(
        self,
        city: Any,
        xy: np.ndarray,
        noise: float,
        rng: np.random.Generator,
        sigma_mult: float = 1.0,
    ) -> None:
        self.city = city
        self.xy = np.asarray(xy)
        self.noise = noise
        self.rng = rng
        d2 = ((city.xy - self.xy) ** 2).sum(1)
        self.d = np.sqrt(d2)
        self.g = np.exp(-d2 / (2 * (SIGMA * sigma_mult) ** 2))
        self.ward = int(city.ward_cell[city.grid.index_of(self.xy)])
        self.mentioned: Set[int] = set()

    def _say(self, j: Optional[int]) -> Optional[str]:
        return None if j is None else corrupt(self.city.poi_names[j], self.noise, self.rng)

    def _pick(self) -> Optional[int]:
        w = self.city.salience * self.g
        if self.mentioned:
            w = w.copy()
            w[list(self.mentioned)] = 0.0
        if self.rng.random() * (w.sum() + C0) < C0:
            return None
        j = int(self.rng.choice(len(w), p=w / w.sum()))
        self.mentioned.add(j)
        return j

    def first(self) -> Tuple[str, Optional[str]]:
        return ("mention", self._say(self._pick()))

    def answer(self, q: Tuple[Any, ...]) -> Tuple[Any, ...]:
        c = self.city
        if q[0] == "landmark":
            return ("mention", self._say(self._pick()))
        if q[0] == "ward":
            if self.rng.random() < P_KNOWS_WARD:
                return ("ward", corrupt(c.ward_names[self.ward], self.noise, self.rng))
            return ("ward", None)
        kind = q[1]
        idxs = c.kind_idx[kind]
        near = idxs[self.d[idxs] <= 200.0]
        if len(near) == 0 or self.rng.random() > P_YES_COVER:
            return ("type_no", kind)
        w = self.g[near]
        j = int(near[int(self.rng.choice(len(near), p=w / w.sum()))])
        return ("type_yes", kind, self._say(j))


POLICIES = ("none", "landmark", "scripted", "adaptive", "adaptive_entropy")


def run_episode(
    city: Any,
    channel: Any,
    policy: str,
    noise: float,
    seed: int,
    budget: int = 4,
    stop_conf: float = 0.85,
    sigma_mult: float = 1.0,
) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    base = city.xy[int(rng.integers(city.n_pois))]
    truth = np.clip(base + rng.normal(0, 120, 2), 0, city.grid.size_m - 1)
    caller = Caller(city, truth, noise, np.random.default_rng(seed + 10_000), sigma_mult)
    eng = LocationEngine(
        city,
        channel,
        seed=seed + 20_000,
        utility="entropy" if policy == "adaptive_entropy" else "conf",
    )
    eng.observe(caller.first())
    asked = 0
    while policy != "none" and asked < budget and eng.confidence() < stop_conf:
        if policy == "landmark":
            q: Tuple[Any, ...] = ("landmark",)
        elif policy == "scripted":
            q = ("ward",) if asked == 0 else ("landmark",)
        else:
            q = eng.choose_adaptive()
        eng.asked.add(q)
        eng.observe(caller.answer(q))
        asked += 1
    est, conf = eng.estimate()
    half = (2 * WINDOW_R + 1) * city.grid.cell_m / 2
    return {
        "err_m": float(np.hypot(*(est - truth))),
        "conf": conf,
        "hit": bool(abs(est[0] - truth[0]) <= half and abs(est[1] - truth[1]) <= half),
        "asked": asked,
    }

