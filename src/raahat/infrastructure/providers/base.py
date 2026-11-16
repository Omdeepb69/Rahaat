"""Shared error types and helpers for external provider adapters.

An adapter either returns data that came from the provider or raises. It never
substitutes a default, a cached guess or an empty result for a failure.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

import httpx


class ProviderError(Exception):
    """A call to an external provider failed."""

    def __init__(self, provider: str, message: str, *, retryable: bool = False) -> None:
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"{provider}: {message}")


class ProviderNotConfigured(ProviderError):
    """The provider has no credentials or endpoint in this deployment."""

    def __init__(self, provider: str, missing: str) -> None:
        self.missing = missing
        super().__init__(provider, f"not configured ({missing} is not set)")


class Stopwatch:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000.0, 1)


@contextmanager
def translate_http_errors(provider: str) -> Iterator[None]:
    """Convert transport and HTTP failures into ProviderError with a safe message."""
    try:
        yield
    except httpx.TimeoutException as exc:
        raise ProviderError(provider, "request timed out", retryable=True) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        retryable = status >= 500 or status == 429
        body = exc.response.text[:200].replace("\n", " ")
        raise ProviderError(provider, f"HTTP {status}: {body}", retryable=retryable) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(provider, f"connection failed: {type(exc).__name__}", retryable=True) from exc
