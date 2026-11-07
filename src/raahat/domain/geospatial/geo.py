"""Grid geometry helpers. Coordinates are metres in a local square map."""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Sequence, Tuple, Union

import numpy as np


@dataclass(frozen=True)
class Grid:
    size_m: float = 6000.0
    cell_m: float = 60.0

    @property
    def n(self) -> int:
        return int(self.size_m // self.cell_m)

    @property
    def ncells(self) -> int:
        return self.n * self.n

    @cached_property
    def centers(self) -> np.ndarray:
        c = (np.arange(self.n) + 0.5) * self.cell_m
        xx, yy = np.meshgrid(c, c, indexing="ij")
        return np.stack([xx.ravel(), yy.ravel()], axis=1)

    def index_of(self, xy: Union[Sequence[float], np.ndarray, Tuple[float, float]]) -> int:
        ix = min(max(int(xy[0] // self.cell_m), 0), self.n - 1)
        iy = min(max(int(xy[1] // self.cell_m), 0), self.n - 1)
        return ix * self.n + iy


def box_sum(p: np.ndarray, n: int, r: int) -> np.ndarray:
    """Sum of p over the (2r+1)x(2r+1) window centred on every cell (zero padded)."""
    a = p.reshape(n, n)
    c = np.zeros((n + 1, n + 1))
    c[1:, 1:] = a.cumsum(0).cumsum(1)
    ix = np.arange(n)
    lo = np.clip(ix - r, 0, n)
    hi = np.clip(ix + r + 1, 0, n)
    s = c[hi][:, hi] - c[lo][:, hi] - c[hi][:, lo] + c[lo][:, lo]
    return s.ravel()

