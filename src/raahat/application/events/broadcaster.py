"""Real-time event broadcaster for Server-Sent Events (SSE) streaming."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from raahat.application.events.models import LiveEvent
from raahat.infrastructure.outbox.repository import OutboxJob

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventBroadcaster:
    """In-memory pub/sub broadcaster distributing real-time SSE events to dispatcher consoles.

    Features:
    - Non-blocking asynchronous streaming
    - Safe subscriber registration and disconnect cleanup
    - Disaster ID filtering (disaster-scoped subscriptions)
    - Keep-alive heartbeat comments
    - Outbox job integration
    """

    def __init__(self) -> None:
        # Each subscriber is (queue, disaster_id_filter, event_loop)
        self._subscribers: set[tuple[asyncio.Queue[Optional[str]], Optional[uuid.UUID], Optional[asyncio.AbstractEventLoop]]] = set()

    @property
    def subscriber_count(self) -> int:
        """Return the number of currently active subscribers."""
        return len(self._subscribers)

    async def subscribe(
        self,
        disaster_id: Optional[uuid.UUID] = None,
        ping_interval_s: float = 15.0,
        max_events: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """Subscribe to the live event stream.

        Yields W3C Server-Sent Event formatted chunks.
        Automatically unregisters on client disconnect or cancellation.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=200)
        sub = (queue, disaster_id, loop)
        self._subscribers.add(sub)
        logger.info(
            "New SSE subscriber connected: disaster_filter=%s, total_subscribers=%d",
            disaster_id,
            len(self._subscribers),
        )

        event_count = 0
        try:
            # Send initial connected confirmation event
            welcome_data = {
                "status": "connected",
                "disaster_id": str(disaster_id) if disaster_id else None,
                "timestamp": _utc_now().isoformat(),
            }
            yield f"event: connected\ndata: {json.dumps(welcome_data, sort_keys=True)}\n\n"
            event_count += 1
            if max_events is not None and event_count >= max_events:
                return

            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=ping_interval_s)
                    if message is None:
                        # Shutdown sentinel received
                        break
                    yield message
                    event_count += 1
                    if max_events is not None and event_count >= max_events:
                        break
                except asyncio.TimeoutError:
                    # Send keep-alive comment to prevent intermediate proxies/NAT from dropping idle connections
                    yield f": keep-alive {_utc_now().isoformat()}\n\n"
        finally:
            self._subscribers.discard(sub)
            logger.info(
                "SSE subscriber disconnected: disaster_filter=%s, remaining_subscribers=%d",
                disaster_id,
                len(self._subscribers),
            )

    def publish(self, event: LiveEvent) -> int:
        """Publish a LiveEvent to all matching subscribers.

        Returns the number of subscribers the event was queued for.
        Non-blocking and thread-safe.
        """
        raw_message = event.format_sse()
        delivered = 0

        for queue, filter_disaster, loop in list(self._subscribers):
            # Check disaster ID filter: None matches all events, otherwise exact match required
            if filter_disaster is not None and event.disaster_id is not None:
                if filter_disaster != event.disaster_id:
                    continue
            elif filter_disaster is not None and event.disaster_id is None:
                # Subscriber filtered by disaster, but event has no disaster associated
                continue

            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(self._safe_enqueue, queue, raw_message)
                else:
                    self._safe_enqueue(queue, raw_message)
                delivered += 1
            except Exception as exc:
                logger.warning("Failed to deliver live event to subscriber queue: %s", exc)

        return delivered

    def publish_from_outbox(self, job: OutboxJob) -> bool:
        """Translate and broadcast an OutboxJob as a LiveEvent."""
        raw_disaster_id = job.payload.get("disaster_id")
        disaster_id: Optional[uuid.UUID] = None
        if raw_disaster_id:
            try:
                disaster_id = uuid.UUID(str(raw_disaster_id))
            except ValueError:
                disaster_id = None

        event = LiveEvent(
            event_id=job.id,
            event_type=job.event_type,
            aggregate_type=job.aggregate_type,
            aggregate_id=job.aggregate_id,
            payload=job.payload,
            disaster_id=disaster_id,
        )
        self.publish(event)
        return True

    def _safe_enqueue(self, queue: asyncio.Queue[Optional[str]], message: Optional[str]) -> None:
        """Put message into queue without raising on QueueFull."""
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("Subscriber queue is full; dropping oldest event to maintain flow.")
            try:
                queue.get_nowait()
                queue.put_nowait(message)
            except Exception:
                pass
