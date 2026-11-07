"""Unit tests for EventBroadcaster, payload sanitization, disaster filtering, and SSE generation."""
from __future__ import annotations

import json
import uuid

import pytest

from raahat.application.events import (
    EventBroadcaster,
    LiveEvent,
    mask_phone_number,
    sanitize_payload,
)
from raahat.infrastructure.outbox.repository import OutboxJob


class TestPayloadSanitization:
    def test_mask_phone_number_various_formats(self) -> None:
        assert mask_phone_number("+919876543210") == "+91987****10"
        assert mask_phone_number("9876543210") == "987654****10"
        assert mask_phone_number("123") == "***"

    def test_sanitize_payload_masks_phones_and_removes_secrets(self) -> None:
        raw_payload = {
            "disaster_id": "123",
            "caller_phone": "+919876543210",
            "mobile_contact": "9876500000",
            "auth_token": "super_secret_jwt",
            "user_password": "my_secret_password",
            "victim": {
                "name": "Ramesh",
                "phone_number": "+919123456789",
                "secret_code": "secret123",
            },
            "teams": [
                {"team_id": "T1", "leader_mobile": "+919988776655"},
            ],
        }

        sanitized = sanitize_payload(raw_payload)

        assert "auth_token" not in sanitized
        assert "user_password" not in sanitized
        assert "secret_code" not in sanitized["victim"]

        assert sanitized["caller_phone"] != "+919876543210"
        assert "****" in sanitized["caller_phone"]
        assert "****" in sanitized["mobile_contact"]
        assert "****" in sanitized["victim"]["phone_number"]
        assert "****" in sanitized["teams"][0]["leader_mobile"]


class TestLiveEventFormatting:
    def test_format_sse_valid_structure(self) -> None:
        event_id = uuid.uuid4()
        disaster_id = uuid.uuid4()
        agg_id = uuid.uuid4()

        event = LiveEvent(
            event_id=event_id,
            event_type="incident.created",
            aggregate_type="incident",
            aggregate_id=agg_id,
            disaster_id=disaster_id,
            payload={"operational_priority": "urgent", "phone": "+919876543210"},
        )

        sse_str = event.format_sse()
        assert sse_str.startswith(f"id: {event_id}\n")
        assert "event: incident.created\n" in sse_str
        assert sse_str.endswith("\n\n")

        # Parse JSON data inside
        lines = sse_str.strip().split("\n")
        data_line = [item for item in lines if item.startswith("data: ")][0]
        data = json.loads(data_line[6:])

        assert data["event_id"] == str(event_id)
        assert data["event_type"] == "incident.created"
        assert data["aggregate_type"] == "incident"
        assert data["aggregate_id"] == str(agg_id)
        assert data["disaster_id"] == str(disaster_id)
        assert "****" in data["payload"]["phone"]


@pytest.mark.asyncio
class TestEventBroadcaster:
    async def test_subscriber_registration_and_cleanup(self) -> None:
        broadcaster = EventBroadcaster()
        assert broadcaster.subscriber_count == 0

        async def consume() -> None:
            gen = broadcaster.subscribe()
            first = await anext(gen)
            assert "event: connected" in first
            assert broadcaster.subscriber_count == 1
            await gen.aclose()

        await consume()
        assert broadcaster.subscriber_count == 0

    async def test_publish_and_receive_event(self) -> None:
        broadcaster = EventBroadcaster()
        disaster_id = uuid.uuid4()

        gen = broadcaster.subscribe(disaster_id=disaster_id)
        connected_msg = await anext(gen)
        assert "event: connected" in connected_msg

        # Publish an event
        event = LiveEvent(
            event_type="operation.event",
            aggregate_type="assignment",
            aggregate_id=uuid.uuid4(),
            disaster_id=disaster_id,
            payload={"status": "en_route"},
        )
        delivered = broadcaster.publish(event)
        assert delivered == 1

        received = await anext(gen)
        assert "event: operation.event" in received
        assert "en_route" in received

        await gen.aclose()

    async def test_disaster_id_filtering(self) -> None:
        broadcaster = EventBroadcaster()
        disaster_a = uuid.uuid4()
        disaster_b = uuid.uuid4()

        # Subscriber 1: listens to Disaster A only
        gen_a = broadcaster.subscribe(disaster_id=disaster_a)
        await anext(gen_a)

        # Subscriber 2: listens to all disasters (global)
        gen_global = broadcaster.subscribe(disaster_id=None)
        await anext(gen_global)

        # Publish event for Disaster B
        event_b = LiveEvent(
            event_type="incident.updated",
            aggregate_type="incident",
            aggregate_id=uuid.uuid4(),
            disaster_id=disaster_b,
            payload={"step": "disaster_b"},
        )
        delivered_b = broadcaster.publish(event_b)
        # Should be delivered ONLY to global subscriber (1), NOT to subscriber A
        assert delivered_b == 1

        received_global = await anext(gen_global)
        assert "disaster_b" in received_global

        # Publish event for Disaster A
        event_a = LiveEvent(
            event_type="incident.updated",
            aggregate_type="incident",
            aggregate_id=uuid.uuid4(),
            disaster_id=disaster_a,
            payload={"step": "disaster_a"},
        )
        delivered_a = broadcaster.publish(event_a)
        # Should be delivered to BOTH subscriber A and global subscriber (2)
        assert delivered_a == 2

        received_a = await anext(gen_a)
        assert "disaster_a" in received_a

        received_global_2 = await anext(gen_global)
        assert "disaster_a" in received_global_2

        await gen_a.aclose()
        await gen_global.aclose()
        assert broadcaster.subscriber_count == 0

    async def test_publish_from_outbox_job(self) -> None:
        broadcaster = EventBroadcaster()
        disaster_id = uuid.uuid4()

        gen = broadcaster.subscribe(disaster_id=disaster_id)
        await anext(gen)

        job = OutboxJob(
            id=uuid.uuid4(),
            aggregate_type="report",
            aggregate_id=uuid.uuid4(),
            event_type="report.ingested",
            payload={"disaster_id": str(disaster_id), "source": "ivr"},
            retry_count=0,
            lease_token=uuid.uuid4(),
        )

        res = broadcaster.publish_from_outbox(job)
        assert res is True

        received = await anext(gen)
        assert "event: report.ingested" in received
        assert "ivr" in received

        await gen.aclose()
