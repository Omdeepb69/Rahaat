"""FastAPI application factory."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from raahat import __version__
from raahat.api.deps import get_session_factory, reset_engine
from raahat.api.routes import (
    alerts,
    audit,
    auth,
    disasters,
    dispatch,
    events,
    incidents,
    public,
    reports,
    resources,
    system,
    users,
)
from raahat.application.events import EventHub
from raahat.config import Settings, get_settings
from raahat.logging_config import configure_logging

logger = logging.getLogger("raahat.api")
access_logger = logging.getLogger("raahat.access")

API_PREFIX = "/api/v1"
AUDIO_UPLOAD_PATH = f"{API_PREFIX}/public/reports/voice"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, enforces the body size limit, and writes one access log line."""

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        limit = (
            self._settings.max_audio_upload_bytes + 64 * 1024
            if request.url.path == AUDIO_UPLOAD_PATH
            else self._settings.max_request_bytes
        )
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                too_large = int(declared) > limit
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    {"detail": "Request body is too large", "request_id": request_id},
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
        elif request.method in ("POST", "PUT", "PATCH"):
            return JSONResponse(
                {"detail": "Content-Length is required", "request_id": request_id},
                status_code=status.HTTP_411_LENGTH_REQUIRED,
            )

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled error", extra={"request_id": request_id, "path": request.url.path})
            response = JSONResponse(
                {"detail": "Internal server error", "request_id": request_id},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        if request.url.path not in ("/health/live", "/health/ready"):
            access_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "user_id": getattr(request.state, "user_id", None),
                },
            )
        return response


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.secret_key_is_ephemeral:
            logger.warning(
                "RAAHAT_SECRET_KEY is not set; using a temporary signing key. "
                "Sessions will not survive a restart."
            )
        app.state.event_hub.start()
        try:
            yield
        finally:
            app.state.event_hub.stop()
            reset_engine()

    app = FastAPI(
        title="RAAHAT API",
        description=(
            "Emergency intake, incident intelligence and rescue-resource coordination. "
            "Decision support: every dispatch requires approval by an authorised person."
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.event_hub = EventHub(settings.database_url)

    app.add_middleware(RequestContextMiddleware, settings=settings)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allowed_origins),
            # Bearer tokens are sent in a header; no cookies are involved.
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
            max_age=600,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"detail": exc.detail, "request_id": getattr(request.state, "request_id", None)},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            {
                "detail": "Some fields are invalid",
                "fields": fields,
                "request_id": getattr(request.state, "request_id", None),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.get("/health/live", tags=["health"], summary="Process is running")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"], summary="Process can serve requests")
    def ready() -> JSONResponse:
        """Checks the database with a real query. Used by the frontend to detect an offline backend."""
        started = time.perf_counter()
        try:
            with get_session_factory()() as session:
                session.execute(text("SELECT 1")).scalar_one()
        except Exception as exc:
            logger.error("Readiness check failed: %s", type(exc).__name__)
            return JSONResponse(
                {"status": "unavailable", "database": "unreachable"},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return JSONResponse(
            {
                "status": "ok",
                "database": "ok",
                "database_latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "version": __version__,
                "server_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )

    for router in (
        auth.router,
        users.router,
        disasters.router,
        reports.router,
        incidents.router,
        resources.router,
        dispatch.router,
        events.router,
        alerts.router,
        audit.router,
        system.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    if settings.public_intake_enabled:
        app.include_router(public.router, prefix=API_PREFIX)

    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn raahat.api.app:app_factory --factory``."""
    return create_app()
