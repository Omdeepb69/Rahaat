"""Realtime operational event stream (Server-Sent Events) and catch-up endpoint."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import StreamingResponse

from raahat.api import scope as access
from raahat.api.deps import CurrentUser, current_user, get_db, get_session_factory
from raahat.application.events import current_sequence, read_events_after, subscribe

router = APIRouter(prefix="/events", tags=["events"])


class EventItem(BaseModel):
    seq: int
    action: str
    entity_type: str
    entity_id: str
    incident_id: Optional[str]
    disaster_id: Optional[str]
    actor_id: Optional[str]
    occurred_at: str
    payload: dict[str, Any]


class EventPage(BaseModel):
    items: list[EventItem]
    head_seq: int


@router.get("/stream", summary="Subscribe to operational changes (SSE)")
async def stream_events(
    request: Request,
    disaster_id: Optional[uuid.UUID] = Query(None),
    max_events: Optional[int] = Query(None, ge=1, le=10_000),
    max_seconds: Optional[float] = Query(None, gt=0, le=3600),
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    user: CurrentUser = Depends(current_user),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> StreamingResponse:
    """Stream committed changes in sequence order.

    Send ``Last-Event-ID`` with the last sequence number received to replay
    anything missed while disconnected. The first message is ``ready``; if its
    ``resync`` flag is true the gap was too large to replay and the client
    must refetch its data. ``heartbeat`` messages arrive every 15 seconds.
    """
    generator = subscribe(
        hub=request.app.state.event_hub,
        session_factory=session_factory,
        last_event_id=last_event_id,
        disaster_id=disaster_id,
        max_events=max_events,
        max_seconds=max_seconds,
        visible=access.visible_operations(user.jurisdiction),
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=EventPage, summary="Read events after a sequence number")
def list_events(
    after: int = Query(0, ge=0),
    disaster_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    user: CurrentUser = Depends(current_user),
    session: Session = Depends(get_db),
) -> EventPage:
    events = read_events_after(
        session, after_seq=after, disaster_id=disaster_id, limit=limit,
        visible=access.visible_operations(user.jurisdiction),
    )
    return EventPage(
        items=[EventItem(**e.__dict__) for e in events],
        head_seq=current_sequence(session),
    )
