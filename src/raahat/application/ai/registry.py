"""Builds provider clients from settings. The one place adapters are constructed."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from raahat.config import Settings, get_settings
from raahat.infrastructure.providers.cap import CapFeedClient
from raahat.infrastructure.providers.geo import NominatimClient, OsrmClient
from raahat.infrastructure.providers.gnani_prisma import GnaniPrismaClient
from raahat.infrastructure.providers.llm import (
    GeminiClient,
    JsonModelClient,
    OpenAICompatibleClient,
)


@dataclass(frozen=True)
class Providers:
    speech: GnaniPrismaClient
    text_model: Optional[JsonModelClient]
    geocoder: NominatimClient
    routing: OsrmClient
    alerts: CapFeedClient


def build_providers(settings: Settings) -> Providers:
    text_model: Optional[JsonModelClient] = None
    if settings.llm_provider == "evon":
        text_model = OpenAICompatibleClient(
            api_base=settings.evon_api_base,
            api_key=settings.evon_api_key,
            model=settings.evon_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    elif settings.llm_provider == "gemini":
        text_model = GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.provider_timeout_seconds,
        )
    return Providers(
        speech=GnaniPrismaClient(
            api_key=settings.gnani_api_key,
            endpoint=settings.prisma_endpoint,
            timeout_seconds=settings.provider_timeout_seconds,
        ),
        text_model=text_model,
        geocoder=NominatimClient(
            enabled=settings.geocoder_provider == "nominatim",
            base_url=settings.nominatim_base_url,
            user_agent=settings.http_user_agent,
            country_codes=settings.geocoder_country_codes,
        ),
        routing=OsrmClient(base_url=settings.osrm_base_url if settings.routing_provider == "osrm" else None),
        alerts=CapFeedClient(feed_url=settings.cap_alert_feed_url, user_agent=settings.http_user_agent),
    )


@lru_cache(maxsize=1)
def get_providers() -> Providers:
    return build_providers(get_settings())
