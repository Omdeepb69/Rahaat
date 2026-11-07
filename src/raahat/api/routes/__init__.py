"""API route modules."""
from __future__ import annotations

from .devices import router as devices_router
from .locations import router as locations_router
from .reports import router as reports_router

__all__ = ["devices_router", "locations_router", "reports_router"]
