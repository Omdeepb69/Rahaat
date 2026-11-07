"""Synthetic gazetteer (landmarks + wards) for simulation and testing.

In production or PostGIS mode, landmark candidates are fetched via spatial queries.
"""
from __future__ import annotations

import numpy as np

from .geo import Grid

SIGMA = 150.0  # metres: how far a caller's mentioned landmark typically is from them

# kind: (salience, name prefixes, suffix, share of POIs)
KINDS = {
    "temple": (
        1.0,
        [
            "Shiv",
            "Ganesh",
            "Hanuman",
            "Ram",
            "Sai Baba",
            "Vitthal",
            "Mahalaxmi",
            "Durga",
            "Krishna",
            "Datta",
            "Khandoba",
            "Jain",
        ],
        "Mandir",
        0.20,
    ),
    "school": (
        0.9,
        [
            "Saraswati",
            "Zilla Parishad",
            "Gandhi",
            "Nehru",
            "Shivaji",
            "Tilak",
            "Ambedkar",
            "Sarvodaya",
        ],
        "Vidyalaya",
        0.14,
    ),
    "petrol_pump": (
        0.9,
        ["Indian Oil", "Bharat Petroleum", "HP", "Reliance", "Nayara"],
        "Petrol Pump",
        0.08,
    ),
    "chowk": (
        1.0,
        [
            "Gandhi",
            "Shivaji",
            "Ambedkar",
            "Nehru",
            "Tilak",
            "Subhash",
            "Bhagat Singh",
            "Savarkar",
        ],
        "Chowk",
        0.14,
    ),
    "bridge": (0.6, ["Nadi", "Railway", "Old", "New", "Kali"], "Pul", 0.05),
    "hospital": (
        0.7,
        ["City", "Sanjivani", "Jeevan", "Government", "Lifeline"],
        "Hospital",
        0.06,
    ),
    "bus_stand": (
        0.8,
        ["Central", "Old", "Market", "Station", "Depot"],
        "Bus Stand",
        0.07,
    ),
    "masjid": (0.8, ["Jama", "Noor", "Madina", "Quba", "Ali"], "Masjid", 0.10),
    "market": (0.8, ["Subzi", "Main", "Weekly", "Fish", "Grain"], "Mandi", 0.08),
}

WARD_NAMES = [
    "kasba",
    "mangalwar peth",
    "shukrawar peth",
    "nehru nagar",
    "gandhi nagar",
    "shivaji nagar",
    "rajiv colony",
    "sai nagar",
    "ambedkar wadi",
    "station road",
    "market yard",
    "river side",
]


class City:
    def __init__(
        self,
        seed: int = 7,
        grid: Grid | None = None,
        n_pois: int = 400,
        n_wards: int = 12,
    ) -> None:
        rng = np.random.default_rng(seed)
        self.grid = grid or Grid()
        size = self.grid.size_m
        kinds = list(KINDS)
        shares = np.array([KINDS[k][3] for k in kinds])
        shares = shares / shares.sum()
        hubs = rng.uniform(0.15 * size, 0.85 * size, (8, 2))

        kind_of: list[str] = []
        names: list[str] = []
        sal: list[float] = []
        xy: list[np.ndarray] = []
        for _ in range(n_pois):
            k = kinds[int(rng.choice(len(kinds), p=shares))]
            s, pre, suf, _ = KINDS[k]
            names.append(f"{pre[int(rng.integers(len(pre)))]} {suf}".lower())
            kind_of.append(k)
            sal.append(s)
            if rng.random() < 0.7:
                p = hubs[int(rng.integers(len(hubs)))] + rng.normal(0, 600, 2)
            else:
                p = rng.uniform(0, size, 2)
            xy.append(np.clip(p, 0, size - 1))

        self.xy = np.array(xy)
        self.salience = np.array(sal)
        self.kind_of = kind_of
        self.poi_names = names
        self.names = sorted(set(names))
        name_id = {n: i for i, n in enumerate(self.names)}
        self.poi_name_id = np.array([name_id[n] for n in names])
        self.name_to_idx = {n: np.where(self.poi_name_id == i)[0] for n, i in name_id.items()}
        self.kind_idx = {k: np.array([i for i, kk in enumerate(kind_of) if kk == k]) for k in kinds}
        self.kinds = [k for k in kinds if len(self.kind_idx[k]) > 0]

        centers = self.grid.centers
        d2 = ((centers[None, :, :] - self.xy[:, None, :]) ** 2).sum(-1)
        self.G = np.exp(-d2 / (2 * SIGMA**2))
        self.D = (self.salience[:, None] * self.G).sum(0)
        self.cover = {k: (d2[idx].min(0) <= 200.0**2) for k, idx in self.kind_idx.items() if len(idx)}

        wc = rng.uniform(0.1 * size, 0.9 * size, (n_wards, 2))
        dw = ((centers[None, :, :] - wc[:, None, :]) ** 2).sum(-1)
        self.ward_cell = np.argmin(dw, axis=0)
        self.ward_names = WARD_NAMES[:n_wards]

    @property
    def n_pois(self) -> int:
        return len(self.poi_names)
