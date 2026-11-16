"""Process-wide service objects built once per application."""
from __future__ import annotations

from functools import lru_cache

from raahat.api.deps import get_session_factory
from raahat.application.ai.registry import Providers, get_providers
from raahat.application.incidents.service import IncidentCommands
from raahat.application.intake.pipeline import ReportPipeline
from raahat.config import get_settings


@lru_cache(maxsize=1)
def get_pipeline() -> ReportPipeline:
    return ReportPipeline(
        settings=get_settings(), providers=get_providers(), session_factory=get_session_factory()
    )


@lru_cache(maxsize=1)
def get_incident_commands() -> IncidentCommands:
    return IncidentCommands(get_session_factory())


def providers() -> Providers:
    return get_providers()


def reset_services() -> None:
    get_pipeline.cache_clear()
    get_incident_commands.cache_clear()
    get_providers.cache_clear()
