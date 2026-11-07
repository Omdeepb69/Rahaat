"""Prometheus metrics endpoint route."""
from __future__ import annotations

from fastapi import APIRouter, Response

from raahat.infrastructure.observability import get_metrics_registry

router = APIRouter(tags=["telemetry"])


@router.get("/metrics", response_class=Response)
def get_prometheus_metrics() -> Response:
    """Expose Prometheus formatted operational metrics for scraping."""
    registry = get_metrics_registry()
    content = registry.render_prometheus()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
