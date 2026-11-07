"""Location belief engine: updates probability distribution over map cells."""
from __future__ import annotations

from typing import Any, List, Optional, Set, Tuple

import numpy as np

from .channel import NameIndex
from .geo import box_sum
from .likelihood import (
    C0,
    P_KNOWS_WARD,
    P_YES_COVER,
    indicator_ll,
    mention_L,
    none_L,
    type_no_L,
    type_yes_L,
    ward_L,
)

WINDOW_R = 2  # (2r+1)^2 cells = 300 m x 300 m window


def _entropy(p: np.ndarray) -> float:
    nz = p > 1e-12
    return float(-(p[nz] * np.log(p[nz])).sum())


def _hb(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return float(-(p * np.log(p) + (1 - p) * np.log(1 - p)))


class LocationEngine:
    def __init__(
        self,
        city: Any,
        channel: Any,
        seed: int = 0,
        noise_discount: float = 0.8,
        mc: int = 16,
        utility: str = "conf",
    ) -> None:
        self.city = city
        self.mc = mc
        self.noise_discount = noise_discount
        self.utility = utility
        self.p = np.full(city.grid.ncells, 1.0 / city.grid.ncells)
        self.rng = np.random.default_rng(seed)
        self.names = NameIndex(city.names, channel)
        self.wards = NameIndex(city.ward_names, channel, k=len(city.ward_names))
        self.asked: Set[Tuple[Any, ...]] = set()
        self._est: Optional[Tuple[np.ndarray, float]] = None

    def _apply(self, L: np.ndarray) -> None:
        q = self.p * L
        s = q.sum()
        if np.isfinite(s) and s > 0:
            self.p = q / s
            self._est = None

    def entropy(self) -> float:
        return _entropy(self.p)

    def estimate(self) -> Tuple[np.ndarray, float]:
        if self._est is None:
            bs = box_sum(self.p, self.city.grid.n, WINDOW_R)
            i = int(np.argmax(bs))
            self._est = (self.city.grid.centers[i], float(bs[i]))
        return self._est

    def confidence(self) -> float:
        return self.estimate()[1]

    def observe(self, obs: Tuple[Any, ...]) -> None:
        kind, c = obs[0], self.city
        if kind == "mention":
            spoken = obs[1]
            if spoken is None:
                self._apply(none_L(c))
            else:
                ll = self.names.scores(spoken)[c.poi_name_id]
                self._apply(mention_L(c, ll, len(spoken)))
        elif kind == "type_yes":
            ll = self.names.scores(obs[2])[c.poi_name_id]
            self._apply(type_yes_L(c, obs[1], ll, len(obs[2])))
        elif kind == "type_no":
            self._apply(type_no_L(c, obs[1]))
        elif kind == "ward" and obs[1] is not None:
            self._apply(ward_L(c, self.wards.scores(obs[1]), len(obs[1])))

    def candidate_questions(self) -> List[Tuple[Any, ...]]:
        qs: List[Tuple[Any, ...]] = [("landmark",)]
        if ("ward",) not in self.asked:
            qs.append(("ward",))
        qs += [("type", k) for k in self.city.kinds if ("type", k) not in self.asked]
        return qs

    def eig(self, q: Tuple[Any, ...]) -> float:
        c, b = self.city, self.p
        conf_mode = self.utility == "conf"
        if q[0] == "ward":
            k = self.noise_discount * P_KNOWS_WARD
            if not conf_mode:
                pw = np.bincount(c.ward_cell, weights=b, minlength=len(c.ward_names))
                return float(k * _entropy(pw))
            n = c.grid.n
            exp_conf = sum(
                float(box_sum(np.where(c.ward_cell == w, b, 0.0), n, WINDOW_R).max())
                for w in range(len(c.ward_names))
            )
            return float(k * (exp_conf - self.confidence()))
        h0 = _entropy(b)
        conf0 = self.confidence()
        cells = self.rng.choice(len(b), size=self.mc, p=b)
        tot = 0.0
        for cell in cells:
            if q[0] == "landmark":
                g = c.salience * c.G[:, cell]
                denom = g.sum() + C0
                if self.rng.random() < C0 / denom:
                    L = none_L(c)
                else:
                    j = int(self.rng.choice(c.n_pois, p=g / g.sum()))
                    ids = c.name_to_idx[c.poi_names[j]]
                    L = (c.salience[ids] @ c.G[ids]) / (c.D + C0)
            else:
                kind = q[1]
                if c.cover[kind][cell] and self.rng.random() < P_YES_COVER:
                    idxs = c.kind_idx[kind]
                    gk = c.G[idxs, cell]
                    j = int(idxs[int(self.rng.choice(len(idxs), p=gk / gk.sum()))])
                    name = c.poi_names[j]
                    L = type_yes_L(c, kind, indicator_ll(c, name), len(name))
                else:
                    L = type_no_L(c, kind)
            post = b * L
            s = post.sum()
            if s <= 0:
                continue
            post = post / s
            if conf_mode:
                tot += float(box_sum(post, c.grid.n, WINDOW_R).max()) - conf0
            else:
                tot += h0 - _entropy(post)
        return float(self.noise_discount * tot / self.mc)

    def choose_adaptive(self) -> Tuple[Any, ...]:
        qs = self.candidate_questions()
        return qs[int(np.argmax([self.eig(q) for q in qs]))]
