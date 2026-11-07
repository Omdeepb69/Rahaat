"""API route modules."""
from __future__ import annotations

from .audit import router as audit_router
from .devices import router as devices_router
from .events import router as events_router
from .incidents import router as incidents_router
from .locations import router as locations_router
from .operations import router as operations_router
from .reports import router as reports_router
from .resources import router as resources_router

__all__ = [
    "audit_router",
    "devices_router",
    "events_router",
    "incidents_router",
    "locations_router",
    "operations_router",
    "reports_router",
    "resources_router",
]
