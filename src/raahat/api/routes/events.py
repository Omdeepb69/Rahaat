"""Real-time live event streaming API routes (Server-Sent Events)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from starlette.responses import StreamingResponse

from raahat.api.dependencies import get_event_broadcaster, require_dispatcher_id
from raahat.application.events import EventBroadcaster

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Subscribe to real-time Server-Sent Events (SSE) live stream",
    response_class=StreamingResponse,
)
async def stream_live_events(
    disaster_id: Optional[uuid.UUID] = Query(
        None, description="Filter live event stream to a specific disaster"
    ),
    max_events: Optional[int] = Query(
        None, ge=1, description="Maximum number of events before closing stream (useful for bounded batches or tests)"
    ),
    dispatcher_id: uuid.UUID = Depends(require_dispatcher_id),
    broadcaster: EventBroadcaster = Depends(get_event_broadcaster),
) -> StreamingResponse:
    """Stream sanitized real-time operational updates to dispatcher consoles.

    Yields Server-Sent Events (SSE) with event types:
    - `connected`: Initial handshake confirmation
    - `report.created` / `report.received`: Sanitized incoming reports
    - `incident.created` / `incident.updated`: Incident status and triage priority changes
    - `operation.assigned` / `operation.event`: Rescue assignments and field team updates
    - `ping`: Periodic keep-alive heartbeat comments
    """
    generator = broadcaster.subscribe(disaster_id=disaster_id, max_events=max_events)
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator, media_type="text/event-stream", headers=headers)
