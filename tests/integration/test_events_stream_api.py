"""Integration tests for Server-Sent Events (SSE) live streaming API."""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from raahat.api.app import app
from raahat.api.dependencies import get_event_broadcaster, get_session_factory
from raahat.application.events import EventBroadcaster, LiveEvent
from raahat.infrastructure.database.session import create_sync_engine, get_sync_sessionmaker

TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:54329/raahat_test",
)


@pytest.fixture(scope="module")
def session_factory() -> sessionmaker[Session]:
    engine = create_sync_engine(TEST_DB_URL)
    return get_sync_sessionmaker(engine)


@pytest.fixture
def test_broadcaster() -> EventBroadcaster:
    return EventBroadcaster()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    test_broadcaster: EventBroadcaster,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_event_broadcaster] = lambda: test_broadcaster
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestEventsStreamAPI:
    def test_stream_unauthorized_without_dispatcher_header(
        self, client: TestClient
    ) -> None:
        res = client.get("/api/v1/events/stream")
        assert res.status_code == 401
        assert "authenticated dispatcher" in res.json()["detail"].lower()

    def test_stream_handshake_via_test_client(
        self, client: TestClient, test_broadcaster: EventBroadcaster
    ) -> None:
        dispatcher_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        res = client.get("/api/v1/events/stream?max_events=1", headers=headers)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        assert "event: connected" in res.text
        assert "status" in res.text
        # Cleaned up after max_events=1
        assert test_broadcaster.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_stream_connected_and_receives_live_events(
        self,
        session_factory: sessionmaker[Session],
        test_broadcaster: EventBroadcaster,
    ) -> None:
        app.dependency_overrides[get_session_factory] = lambda: session_factory
        app.dependency_overrides[get_event_broadcaster] = lambda: test_broadcaster

        dispatcher_id = uuid.uuid4()
        disaster_id = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            async def event_pusher() -> None:
                while test_broadcaster.subscriber_count == 0:
                    await asyncio.sleep(0.01)
                event = LiveEvent(
                    event_type="incident.updated",
                    aggregate_type="incident",
                    aggregate_id=uuid.uuid4(),
                    disaster_id=disaster_id,
                    payload={"status": "in_progress", "caller_phone": "+919876543210"},
                )
                test_broadcaster.publish(event)

            push_task = asyncio.create_task(event_pusher())

            res = await async_client.get(
                f"/api/v1/events/stream?disaster_id={disaster_id}&max_events=2",
                headers=headers,
            )
            await push_task

            assert res.status_code == 200
            assert "text/event-stream" in res.headers.get("content-type", "")

            body = res.text
            assert "event: connected" in body
            assert "event: incident.updated" in body
            assert "in_progress" in body
            # Phone should be sanitized
            assert "****" in body
            assert "+919876543210" not in body

        assert test_broadcaster.subscriber_count == 0
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_stream_disaster_id_filtering(
        self,
        session_factory: sessionmaker[Session],
        test_broadcaster: EventBroadcaster,
    ) -> None:
        app.dependency_overrides[get_session_factory] = lambda: session_factory
        app.dependency_overrides[get_event_broadcaster] = lambda: test_broadcaster

        dispatcher_id = uuid.uuid4()
        disaster_target = uuid.uuid4()
        disaster_other = uuid.uuid4()
        headers = {"X-Dispatcher-Id": str(dispatcher_id)}

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            async def event_pusher() -> None:
                while test_broadcaster.subscriber_count == 0:
                    await asyncio.sleep(0.01)
                # First publish event for unrelated disaster
                test_broadcaster.publish(
                    LiveEvent(
                        event_type="incident.other",
                        aggregate_type="incident",
                        aggregate_id=uuid.uuid4(),
                        disaster_id=disaster_other,
                        payload={"info": "unrelated"},
                    )
                )
                # Then publish event for target disaster
                test_broadcaster.publish(
                    LiveEvent(
                        event_type="incident.target",
                        aggregate_type="incident",
                        aggregate_id=uuid.uuid4(),
                        disaster_id=disaster_target,
                        payload={"info": "target_event"},
                    )
                )

            push_task = asyncio.create_task(event_pusher())

            res = await async_client.get(
                f"/api/v1/events/stream?disaster_id={disaster_target}&max_events=2",
                headers=headers,
            )
            await push_task

            assert res.status_code == 200
            body = res.text

            # Handshake
            assert "event: connected" in body
            # Must receive incident.target, NOT incident.other!
            assert "event: incident.target" in body
            assert "target_event" in body
            assert "incident.other" not in body

        assert test_broadcaster.subscriber_count == 0
        app.dependency_overrides.clear()
