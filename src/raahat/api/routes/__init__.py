"""API route modules."""
from __future__ import annotations

from .locations import router as locations_router
from .reports import router as reports_router

__all__ = ["locations_router", "reports_router"]
