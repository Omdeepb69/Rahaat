"""Import and list official alerts from a CAP feed.

Stored verbatim in external_observations with their provenance. The interface
shows who issued each alert, when it was issued, when it expires and when
RAAHAT fetched it. Alerts are reference information: they never create
incidents or change priorities.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from raahat.application.system.status import record_integration_result
from raahat.infrastructure.database.models.system import ExternalObservationModel
from raahat.infrastructure.providers.base import ProviderError
from raahat.infrastructure.providers.cap import CapFeedClient, alert_payload

MAX_NEW_PER_POLL = 25


def provider_for(feed_url: str) -> tuple[str, str]:
    """(provider name, authority). Only the NDMA SACHET system is treated as official."""
    host = (urlparse(feed_url).hostname or "").lower()
    if host == "sachet.ndma.gov.in":
        return "ndma_sachet", "official"
    return "cap_feed", "unverified"


def poll(session: Session, client: CapFeedClient) -> dict[str, Any]:
    """Fetch new alerts and store them. Records the outcome as integration status. Commits."""
    assert client.feed_url
    provider, authority = provider_for(client.feed_url)
    known = set(
        session.execute(
            select(ExternalObservationModel.external_id).where(ExternalObservationModel.provider == provider)
        ).scalars()
    )
    try:
        results, errors, duration = client.fetch(skip=known, limit=MAX_NEW_PER_POLL)
    except ProviderError as exc:
        record_integration_result(session, "alerts", ok=False, detail=str(exc))
        session.commit()
        return {"stored": 0, "error": str(exc)}

    now = datetime.now(timezone.utc)
    for item, alert in results:
        statement = insert(ExternalObservationModel).values(
            id=uuid.uuid4(),
            provider=provider,
            external_id=item.guid,
            kind="alert",
            authority=authority,
            headline=alert.headline or item.title or "(no headline)",
            severity=alert.severity,
            area_description=alert.area_description,
            issued_at=alert.sent or item.published_at,
            expires_at=alert.expires,
            fetched_at=now,
            source_url=item.link,
            payload=alert_payload(item, alert),
            created_at=now,
        )
        session.execute(statement.on_conflict_do_nothing(index_elements=["provider", "external_id"]))
    detail = f"Feed read; {len(results)} new alert(s)"
    if errors:
        detail += f"; {len(errors)} message(s) could not be read"
    record_integration_result(session, "alerts", ok=True, detail=detail, latency_ms=duration)
    session.commit()
    return {"stored": len(results), "errors": errors}


def list_alerts(
    session: Session, *, active_only: bool, limit: int = 100, offset: int = 0
) -> tuple[list[ExternalObservationModel], int, Optional[datetime]]:
    clauses = ["kind = 'alert'"]
    if active_only:
        clauses.append("(expires_at IS NULL OR expires_at > now())")
    where = " AND ".join(clauses)
    total = session.execute(text(f"SELECT count(*) FROM external_observations WHERE {where}")).scalar_one()
    rows = session.execute(
        select(ExternalObservationModel)
        .where(text(where))
        .order_by(ExternalObservationModel.issued_at.desc().nullslast())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    last_fetch = session.execute(text("SELECT max(fetched_at) FROM external_observations WHERE kind = 'alert'")).scalar_one()
    return list(rows), total, last_fetch
