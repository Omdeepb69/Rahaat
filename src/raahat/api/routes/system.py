"""System and integration status."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, get_db, require
from raahat.api.services import providers
from raahat.application.system import status as system_status
from raahat.config import Settings, get_settings
from raahat.infrastructure.database.repositories.audit import append_audit
from raahat.security.permissions import Permission

router = APIRouter(prefix="/system", tags=["system"])


class Component(BaseModel):
    key: str
    name: str
    group: str
    status: str
    detail: str
    checked_at: Optional[datetime]
    last_success_at: Optional[datetime]
    latency_ms: Optional[float]
    required: bool
    can_probe: bool
    metrics: dict[str, Any]


class SystemStatus(BaseModel):
    overall: str
    environment: str
    version: str
    generated_at: datetime
    components: list[Component]
    notices: list[str]


def _component(component: system_status.ComponentStatus) -> Component:
    return Component(**component.__dict__)


@router.get("/status", response_model=SystemStatus, summary="Health of every component and integration")
def get_status(
    request: Request,
    _: CurrentUser = Depends(require(Permission.SYSTEM_READ)),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SystemStatus:
    components = [
        system_status.check_database(session),
        system_status.check_worker(session, settings),
        system_status.check_realtime(request.app.state.event_hub.status()),
        system_status.check_host(settings),
        *system_status.integration_statuses(session, settings, providers()),
    ]
    notices: list[str] = []
    if settings.secret_key_is_ephemeral:
        notices.append(
            "RAAHAT_SECRET_KEY is not set. A temporary signing key is in use and every "
            "session ends when the API restarts."
        )
    if not settings.cors_allowed_origins:
        notices.append("CORS_ALLOWED_ORIGINS is empty: browsers on other origins cannot call this API.")
    if settings.public_intake_enabled:
        notices.append("Public citizen intake is enabled: unauthenticated report submission is open.")
    return SystemStatus(
        overall=system_status.overall(components), environment=settings.environment,
        version=request.app.version, generated_at=datetime.now().astimezone(),
        components=[_component(c) for c in components], notices=notices,
    )


@router.post("/integrations/{key}/probe", response_model=Component, summary="Run a live check against a provider")
def probe(
    key: str,
    actor: CurrentUser = Depends(require(Permission.SYSTEM_MANAGE)),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Component:
    """Makes one real request to the provider and records the outcome."""
    try:
        component = system_status.run_probe(session, key, settings, providers())
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    import uuid

    append_audit(
        session, action="system.integration_probed", actor_id=actor.id, entity_type="integration",
        entity_id=uuid.uuid5(uuid.NAMESPACE_URL, f"raahat:integration:{key}"),
        payload={"integration": key, "status": component.status},
    )
    session.commit()
    return _component(component)
