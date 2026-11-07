"""FastAPI application factory for Raahat 2.0."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from raahat.api.routes.reports import router as reports_router


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
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "raahat-api"}

    # Register API routers
    app.include_router(reports_router, prefix="/api/v1")

    return app


app = create_app()

