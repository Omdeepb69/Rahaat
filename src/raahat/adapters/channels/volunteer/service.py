"""Device synchronization service: ingests batches, updates cursors, and suppresses duplicates."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session, sessionmaker

from field_app.models import SyncAck, SyncBatch
from raahat.adapters.channels.volunteer.adapter import VolunteerSyncAdapter
from raahat.application.ingestion import ReportIngestionService
from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.sync import SyncCursorModel
from raahat.infrastructure.outbox import DomainEvent, EventOutbox, PostgresEventOutbox

logger = logging.getLogger(__name__)


class DeviceSyncService:
    """Server-side coordinator for field device batch synchronization."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        ingestion_service: Optional[ReportIngestionService] = None,
        outbox: Optional[EventOutbox] = None,
    ) -> None:
        self._session_factory = session_factory
        self._ingestion_service = (
            ingestion_service or ReportIngestionService(session_factory=session_factory)
        )
        self._outbox = outbox or PostgresEventOutbox()

    def sync_batch(
        self,
        authenticated_device_id: uuid.UUID,
        batch: SyncBatch,
    ) -> SyncAck:
        """Ingest a batch of offline reports with strict idempotency and cursor tracking.

        Guarantees that retransmitted batches are acknowledged without duplicate report creation.
        """
        if authenticated_device_id != batch.device_id:
            raise PermissionError("Authenticated device ID does not match batch payload")

        server_synced_at = utc_now()
        accepted_count = 0
        duplicate_count = 0

        # 1. Ingest each report item via ReportIngestionService
        for item in batch.items:
            submission = VolunteerSyncAdapter.to_submission(
                device_id=batch.device_id,
                item=item,
                batch_id=batch.batch_id,
            )
            result = self._ingestion_service.ingest(submission)
            if result.is_duplicate:
                duplicate_count += 1
            else:
                accepted_count += 1

        # 2. Advance device sync cursor atomically
        with self._session_factory() as session:
            cursor = (
                session.query(SyncCursorModel)
                .filter_by(device_id=batch.device_id)
                .first()
            )
            new_last_seq = (
                max(cursor.last_sequence, batch.to_sequence)
                if cursor is not None
                else batch.to_sequence
            )
            metadata = {
                "last_batch_id": str(batch.batch_id),
                "from_sequence": batch.from_sequence,
                "to_sequence": batch.to_sequence,
                "accepted_count": accepted_count,
                "duplicate_count": duplicate_count,
            }

            if cursor is None:
                cursor = SyncCursorModel(
                    id=uuid.uuid4(),
                    device_id=batch.device_id,
                    last_sequence=new_last_seq,
                    last_synced_at=server_synced_at,
                    sync_metadata=metadata,
                )
                session.add(cursor)
            else:
                cursor.last_sequence = new_last_seq
                cursor.last_synced_at = server_synced_at
                cursor.sync_metadata = metadata

            # 3. Publish device.synced event to transactional outbox
            event = DomainEvent(
                event_type="raahat.device.synced",
                aggregate_type="device",
                aggregate_id=batch.device_id,
                payload={
                    "device_id": str(batch.device_id),
                    "batch_id": str(batch.batch_id),
                    "from_sequence": batch.from_sequence,
                    "to_sequence": batch.to_sequence,
                    "accepted_count": accepted_count,
                    "duplicate_count": duplicate_count,
                    "server_synced_at": server_synced_at.isoformat(),
                },
                occurred_at=server_synced_at,
            )
            self._outbox.publish(event, session)
            session.commit()

        logger.info(
            "Device sync batch completed",
            extra={
                "device_id": str(batch.device_id),
                "batch_id": str(batch.batch_id),
                "accepted": accepted_count,
                "duplicates": duplicate_count,
                "acknowledged_seq": batch.to_sequence,
            },
        )

        return SyncAck(
            device_id=batch.device_id,
            batch_id=batch.batch_id,
            server_synced_at=server_synced_at,
            acknowledged_sequence=batch.to_sequence,
            accepted_count=accepted_count,
            duplicate_count=duplicate_count,
        )

    def get_device_cursor(self, device_id: uuid.UUID) -> Optional[dict[str, Any]]:
        """Retrieve current sync cursor for a given device ID."""
        with self._session_factory() as session:
            cursor = (
                session.query(SyncCursorModel)
                .filter_by(device_id=device_id)
                .first()
            )
            if not cursor:
                return None
            return {
                "device_id": str(cursor.device_id),
                "last_sequence": cursor.last_sequence,
                "last_synced_at": cursor.last_synced_at.isoformat(),
                "sync_metadata": cursor.sync_metadata,
            }
