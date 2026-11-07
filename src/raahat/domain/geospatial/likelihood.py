"""Likelihood vectors over map cells for each kind of observation.

Generative model for a landmark mention: a caller at x names POI i with probability
  P(i | x) = s_i * g_i(x) / (D(x) + C0),   g_i(x) = exp(-|x - p_i|^2 / (2 sigma^2)),
and says nothing identifiable with probability C0 / (D(x) + C0).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

Q_GARBAGE = 0.05
C0 = 0.02
P_YES_COVER = 0.95
P_YES_NOCOVER = 0.01
P_NO_NOCOVER = 0.99
P_KNOWS_WARD = 0.85
LOG_UNIFORM_CHAR = -math.log(27)


def _garbage(spoken_len: int) -> float:
    return math.log(Q_GARBAGE) + spoken_len * LOG_UNIFORM_CHAR


def indicator_ll(city: Any, name: str) -> np.ndarray:
    """Noise-free log-likelihood vector over POIs: 0 for POIs with this name, -inf elsewhere."""
    ll = np.full(city.n_pois, -np.inf)
    ll[city.name_to_idx[name]] = 0.0
    return ll


def none_L(city: Any) -> np.ndarray:
    return np.asarray(C0 / (city.D + C0))


def mention_L(city: Any, ll_poi: np.ndarray, spoken_len: int) -> np.ndarray:
    logw = np.log(city.salience) + ll_poi
    lg = _garbage(spoken_len)
    m = max(float(np.max(logw)), lg)
    w = np.exp(logw - m)
    return np.asarray((w @ city.G) / (city.D + C0) + math.exp(lg - m))


def type_yes_L(city: Any, kind: str, ll_poi: np.ndarray, spoken_len: int) -> np.ndarray:
    idx = city.kind_idx[kind]
    gt = city.G[idx]
    lg = _garbage(spoken_len)
    logw = ll_poi[idx]
    m = max(float(np.max(logw)), lg)
    w = np.exp(logw - m)
    name_part = (w @ gt) / (gt.sum(0) + 1e-6)
    pyes = np.where(city.cover[kind], P_YES_COVER, P_YES_NOCOVER)
    return np.asarray(pyes * (name_part + math.exp(lg - m)))


def type_no_L(city: Any, kind: str) -> np.ndarray:
    return np.asarray(np.where(city.cover[kind], 1 - P_YES_COVER, P_NO_NOCOVER))


def ward_L(city: Any, ll_ward: np.ndarray, spoken_len: int) -> np.ndarray:
    lg = _garbage(spoken_len)
    m = max(float(np.max(ll_ward)), lg)
    w = np.exp(ll_ward - m)
    return np.asarray(w[city.ward_cell] + math.exp(lg - m))
