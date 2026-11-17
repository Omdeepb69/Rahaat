"""In-process sliding-window rate limiter.

The API runs as a single process (see README.md, Measured performance), so process-local
state is authoritative. Memory is bounded: idle keys are pruned and the key
table is capped.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int


class SlidingWindowLimiter:
    def __init__(self, *, max_keys: int = 20_000) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float = 60.0,
        now: float | None = None,
    ) -> RateDecision:
        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                if len(self._hits) >= self._max_keys:
                    self._prune(cutoff)
                hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(hits[0] + window_seconds - current) + 1)
                return RateDecision(False, retry_after)
            hits.append(current)
            return RateDecision(True, 0)

    def _prune(self, cutoff: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
        if len(self._hits) >= self._max_keys:
            # Still full of active keys: drop the oldest half rather than grow.
            for key in list(self._hits)[: self._max_keys // 2]:
                del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
