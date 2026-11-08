"""FastAPI application factory for Raahat 2.0."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from raahat.api.routes.audit import router as audit_router
from raahat.api.routes.demo import router as demo_router
from raahat.api.routes.devices import router as devices_router
from raahat.api.routes.disasters import router as disasters_router
from raahat.api.routes.events import router as events_router
from raahat.api.routes.incidents import router as incidents_router
from raahat.api.routes.ivr import router as ivr_router
from raahat.api.routes.locations import router as locations_router
from raahat.api.routes.metrics import router as metrics_router
from raahat.api.routes.operations import router as operations_router
from raahat.api.routes.reports import router as reports_router
from raahat.api.routes.resources import router as resources_router
from raahat.api.routes.workflow import router as workflow_router


def create_app() -> FastAPI:
    """Create and configure the Raahat FastAPI application."""
    app = FastAPI(
        title="Raahat 2.0 Disaster Intelligence API",
        description="Multichannel disaster intelligence, uncertainty-aware triage, and rescue coordination platform.",
        version="0.2.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["health"])
    @app.get("/health/live", tags=["health"])
    @app.get("/health/ready", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "raahat-api"}

    # Register API routers
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(incidents_router, prefix="/api/v1")
    app.include_router(disasters_router, prefix="/api/v1")
    app.include_router(locations_router, prefix="/api/v1")
    app.include_router(devices_router, prefix="/api/v1")
    app.include_router(resources_router, prefix="/api/v1")
    app.include_router(operations_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")
    app.include_router(workflow_router, prefix="/api/v1")
    app.include_router(ivr_router, prefix="/api/v1")
    app.include_router(demo_router, prefix="/api/v1")
    app.include_router(metrics_router, prefix="/api/v1")
    app.include_router(metrics_router)  # exposes /metrics at root for standard Prometheus scraping

    # Mount Operator Console web application
    console_dir = Path(__file__).resolve().parent.parent.parent.parent / "operator_console"
    if console_dir.exists() and (console_dir / "public").exists():
        if (console_dir / "src").exists():
            app.mount("/console/src", StaticFiles(directory=str(console_dir / "src")), name="console-src")
        app.mount("/console", StaticFiles(directory=str(console_dir / "public"), html=True), name="console")

    # Mount Citizen SOS portal
    citizen_dir = Path(__file__).resolve().parent.parent.parent.parent / "citizen_portal"
    if citizen_dir.exists() and (citizen_dir / "public").exists():
        if (citizen_dir / "src").exists():
            app.mount("/sos/src", StaticFiles(directory=str(citizen_dir / "src")), name="sos-src")
        app.mount("/sos", StaticFiles(directory=str(citizen_dir / "public"), html=True), name="sos")

    @app.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/console/")

    return app


app = create_app()

