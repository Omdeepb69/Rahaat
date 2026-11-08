"""API route modules."""
from __future__ import annotations

from .audit import router as audit_router
from .demo import router as demo_router
from .devices import router as devices_router
from .disasters import router as disasters_router
from .events import router as events_router
from .incidents import router as incidents_router
from .ivr import router as ivr_router
from .locations import router as locations_router
from .metrics import router as metrics_router
from .operations import router as operations_router
from .reports import router as reports_router
from .resources import router as resources_router
from .workflow import router as workflow_router

__all__ = [
    "audit_router",
    "demo_router",
    "devices_router",
    "disasters_router",
    "events_router",
    "incidents_router",
    "ivr_router",
    "locations_router",
    "metrics_router",
    "operations_router",
    "reports_router",
    "resources_router",
    "workflow_router",
]
