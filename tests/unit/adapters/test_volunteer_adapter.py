"""Unit tests for VolunteerSyncAdapter."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from field_app.models import SyncReportItem
from raahat.adapters.channels.volunteer.adapter import VolunteerSyncAdapter
from raahat.domain.shared.enums import SourceType


def test_volunteer_sync_adapter_to_submission() -> None:
    device_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    disaster_id = uuid.uuid4()
    event_id = uuid.uuid4()
    created_at = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)

    item = SyncReportItem(
        event_id=event_id,
        sequence=3,
        disaster_id=disaster_id,
        raw_payload={"people_count": 4, "needs": ["rescue"]},
        client_created_at=created_at,
        idempotency_key=f"volunteer:{device_id}:3",
        source_identity="Volunteer Ramesh",
        language_code="hi",
    )

    submission = VolunteerSyncAdapter.to_submission(
        device_id=device_id,
        item=item,
        batch_id=batch_id,
    )

    assert submission.disaster_id == disaster_id
    assert submission.source_type == SourceType.VOLUNTEER
    assert submission.source_event_id == str(event_id)
    assert submission.device_id == device_id
    assert submission.source_identity == "Volunteer Ramesh"
    assert submission.channel_reference == f"batch:{batch_id}:seq:3"
    assert submission.raw_payload == {"people_count": 4, "needs": ["rescue"]}
    assert submission.client_created_at == created_at
    assert submission.language_code == "hi"
    assert submission.idempotency_key == f"volunteer:{device_id}:3"
