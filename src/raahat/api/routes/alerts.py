"""Official alerts imported from a CAP feed."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from raahat.api.deps import CurrentUser, get_db, require
from raahat.api.schemas import Pagination
from raahat.application.alerts.service import list_alerts
from raahat.config import Settings, get_settings
from raahat.security.permissions import Permission

router = APIRouter(prefix="/alerts", tags=["alerts"])


class Alert(BaseModel):
    id: uuid.UUID
    provider: str
    authority: str
    headline: str
    severity: Optional[str]
    area_description: Optional[str]
    issued_at: Optional[datetime]
    expires_at: Optional[datetime]
    fetched_at: datetime
    source_url: Optional[str]
    details: dict[str, Any]


class AlertPage(BaseModel):
    configured: bool
    feed_url: Optional[str]
    last_fetched_at: Optional[datetime]
    items: list[Alert]
    total: int
    limit: int
    offset: int


@router.get("", response_model=AlertPage, summary="Alerts from the configured official feed")
def alerts(
    active_only: bool = Query(True),
    page: Pagination = Depends(),
    _: CurrentUser = Depends(require(Permission.INCIDENTS_READ)),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AlertPage:
    rows, total, last = list_alerts(session, active_only=active_only, limit=page.limit, offset=page.offset)
    return AlertPage(
        configured=bool(settings.cap_alert_feed_url),
        feed_url=settings.cap_alert_feed_url,
        last_fetched_at=last,
        items=[
            Alert(
                id=r.id, provider=r.provider, authority=r.authority, headline=r.headline, severity=r.severity,
                area_description=r.area_description, issued_at=r.issued_at, expires_at=r.expires_at,
                fetched_at=r.fetched_at, source_url=r.source_url, details=r.payload or {},
            )
            for r in rows
        ],
        total=total, limit=page.limit, offset=page.offset,
    )
