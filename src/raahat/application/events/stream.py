"""Realtime event stream backed by the persisted audit log.

Every operational change appends a row to ``audit_events`` with a sequence
number; an insert trigger issues ``NOTIFY raahat_events``. Each API process
runs one listener thread that wakes subscribers when a notification arrives.
Subscribers then read rows after their own cursor, so:

* an event is delivered only after its transaction has committed;
* a subscriber that reconnects with its last sequence number receives
  everything it missed;
* a missed notification costs latency, not data: subscribers also re-check on
  a timer.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

import psycopg
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from raahat.infrastructure.database.models.audit import AuditEventModel

logger = logging.getLogger(__name__)

CHANNEL = "raahat_events"
REPLAY_LIMIT = 500
BATCH_LIMIT = 200
HEARTBEAT_SECONDS = 15.0
RECHECK_SECONDS = 5.0

# Account housekeeping is audited but is not operational traffic.
_NON_STREAMED_PREFIXES = ("user.login",)


@dataclass(frozen=True)
class StreamEvent:
    seq: int
    action: str
    entity_type: str
    entity_id: str
    incident_id: Optional[str]
    disaster_id: Optional[str]
    actor_id: Optional[str]
    occurred_at: str
    payload: dict[str, Any]

    def to_sse(self) -> str:
        data = {
            "seq": self.seq,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "incident_id": self.incident_id,
            "disaster_id": self.disaster_id,
            "actor_id": self.actor_id,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
        return f"id: {self.seq}\nevent: change\ndata: {json.dumps(data, default=str)}\n\n"


def _to_event(row: AuditEventModel) -> StreamEvent:
    return StreamEvent(
        seq=row.seq,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=str(row.entity_id),
        incident_id=str(row.incident_id) if row.incident_id else None,
        disaster_id=str(row.disaster_id) if row.disaster_id else None,
        actor_id=str(row.actor_id) if row.actor_id else None,
        occurred_at=row.created_at.isoformat(),
        payload=row.payload or {},
    )


def current_sequence(session: Session) -> int:
    return session.execute(select(func.coalesce(func.max(AuditEventModel.seq), 0))).scalar_one()


def read_events_after(
    session: Session,
    *,
    after_seq: int,
    disaster_id: Optional[UUID] = None,
    limit: int = BATCH_LIMIT,
) -> list[StreamEvent]:
    stmt = select(AuditEventModel).where(AuditEventModel.seq > after_seq)
    if disaster_id is not None:
        stmt = stmt.where(
            (AuditEventModel.disaster_id == disaster_id) | (AuditEventModel.disaster_id.is_(None))
        )
    for prefix in _NON_STREAMED_PREFIXES:
        stmt = stmt.where(~AuditEventModel.action.startswith(prefix))
    rows = session.execute(stmt.order_by(AuditEventModel.seq.asc()).limit(limit)).scalars().all()
    return [_to_event(r) for r in rows]


class EventHub:
    """One LISTEN connection per process, fanning wake-ups out to subscribers."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._last_notification_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="raahat-event-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                with psycopg.connect(self._database_url, autocommit=True) as conn:
                    conn.execute(f"LISTEN {CHANNEL}")
                    self._connected = True
                    self._last_error = None
                    backoff = 1.0
                    # Anything committed while the listener was down is picked
                    # up by this wake-up.
                    self._wake_all()
                    while not self._stop.is_set():
                        received = False
                        for _ in conn.notifies(timeout=1.0, stop_after=50):
                            received = True
                        if received:
                            self._last_notification_at = datetime.now(timezone.utc)
                            self._wake_all()
            except Exception as exc:  # connection lost or database unavailable
                self._connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Event listener disconnected: %s; retrying in %.0fs", exc, backoff)
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 15.0)
        self._connected = False

    # -- fan-out -------------------------------------------------------------
    def _wake_all(self) -> None:
        with self._lock:
            targets = list(self._subscribers)
        for loop, event in targets:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # loop already closed
                pass

    def register(self) -> tuple[asyncio.AbstractEventLoop, asyncio.Event]:
        entry = (asyncio.get_running_loop(), asyncio.Event())
        with self._lock:
            self._subscribers.add(entry)
        return entry

    def unregister(self, entry: tuple[asyncio.AbstractEventLoop, asyncio.Event]) -> None:
        with self._lock:
            self._subscribers.discard(entry)

    # -- status --------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        with self._lock:
            subscribers = len(self._subscribers)
        return {
            "listening": self._connected,
            "subscribers": subscribers,
            "last_notification_at": self._last_notification_at,
            "last_error": self._last_error,
        }


async def subscribe(
    *,
    hub: EventHub,
    session_factory: sessionmaker[Session],
    last_event_id: Optional[int],
    disaster_id: Optional[UUID],
    max_events: Optional[int] = None,
    max_seconds: Optional[float] = None,
) -> AsyncGenerator[str, None]:
    """Yield Server-Sent Events: a handshake, any missed events, then live ones."""

    def _read(after: int) -> list[StreamEvent]:
        with session_factory() as session:
            return read_events_after(session, after_seq=after, disaster_id=disaster_id)

    def _head() -> int:
        with session_factory() as session:
            return current_sequence(session)

    head = await asyncio.to_thread(_head)
    resync = False
    if last_event_id is None:
        cursor = head
    elif last_event_id > head or head - last_event_id > REPLAY_LIMIT:
        # The client's cursor is ahead of this database (restored from backup)
        # or too far behind to replay. It must refetch its state.
        cursor = head
        resync = True
    else:
        cursor = last_event_id

    entry = hub.register()
    _, wake = entry
    started = time.monotonic()
    sent = 0
    try:
        hello = {
            "seq": cursor,
            "resync": resync,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
        yield f"retry: 3000\nevent: ready\ndata: {json.dumps(hello)}\n\n"

        last_beat = time.monotonic()
        while True:
            events = await asyncio.to_thread(_read, cursor)
            for event in events:
                cursor = event.seq
                yield event.to_sse()
                sent += 1
                if max_events is not None and sent >= max_events:
                    return
            if len(events) >= BATCH_LIMIT:
                continue  # more may be waiting
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                return

            wake.clear()
            try:
                await asyncio.wait_for(wake.wait(), timeout=RECHECK_SECONDS)
            except asyncio.TimeoutError:
                pass
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                last_beat = time.monotonic()
                beat = {"server_time": datetime.now(timezone.utc).isoformat(), "seq": cursor}
                yield f"event: heartbeat\ndata: {json.dumps(beat)}\n\n"
    finally:
        hub.unregister(entry)
