"""Outbound offline synchronization queue and monotonic sequence coordinator."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

from field_app.database.connection import DatabaseManager
from field_app.models import (
    OfflineReport,
    OfflineReportDraft,
    SyncAck,
    SyncBatch,
    SyncReportItem,
    SyncStatus,
    utc_now,
)


def _row_to_report(row: sqlite3.Row) -> OfflineReport:
    """Map SQLite row to frozen OfflineReport model."""
    return OfflineReport(
        id=uuid.UUID(row["id"]),
        device_id=uuid.UUID(row["device_id"]),
        sequence=row["sequence"],
        disaster_id=uuid.UUID(row["disaster_id"]),
        raw_payload=json.loads(row["raw_payload"]),
        source_identity=row["source_identity"],
        language_code=row["language_code"],
        client_created_at=datetime.fromisoformat(row["client_created_at"]),
        idempotency_key=row["idempotency_key"],
        sync_status=SyncStatus(row["sync_status"]),
        batch_id=uuid.UUID(row["batch_id"]) if row["batch_id"] else None,
        synced_at=datetime.fromisoformat(row["synced_at"]) if row["synced_at"] else None,
        error_message=row["error_message"],
    )


class OfflineSyncQueue:
    """Manages offline drafting, monotonic sequence assignment, and sync lifecycle."""

    def __init__(
        self,
        device_id: uuid.UUID,
        db: DatabaseManager,
        device_name: Optional[str] = None,
    ) -> None:
        self.device_id = device_id
        self.db = db
        self._ensure_device_registered(device_name)

    def _ensure_device_registered(self, device_name: Optional[str] = None) -> None:
        """Register device state in SQLite if not yet recorded."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT device_id FROM device_state WHERE device_id = ?;",
                (str(self.device_id),),
            )
            if not cursor.fetchone():
                conn.execute(
                    """
                    INSERT INTO device_state (device_id, current_sequence, registered_at, device_name)
                    VALUES (?, 0, ?, ?);
                    """,
                    (str(self.device_id), utc_now().isoformat(), device_name),
                )

    def get_current_sequence(self) -> int:
        """Get the latest monotonic sequence number recorded by this device."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT current_sequence FROM device_state WHERE device_id = ?;",
                (str(self.device_id),),
            )
            row = cursor.fetchone()
            return int(row["current_sequence"]) if row else 0

    def enqueue_report(self, draft: OfflineReportDraft) -> OfflineReport:
        """Persist a report drafted offline with an atomically incremented sequence number.

        Guarantees strictly monotonic sequence numbering and immediate local durability.
        """
        report_id = uuid.uuid4()

        with self.db.transaction() as conn:
            # 1. Atomically advance device sequence number
            conn.execute(
                """
                UPDATE device_state
                SET current_sequence = current_sequence + 1
                WHERE device_id = ?;
                """,
                (str(self.device_id),),
            )
            cursor = conn.execute(
                "SELECT current_sequence FROM device_state WHERE device_id = ?;",
                (str(self.device_id),),
            )
            seq = int(cursor.fetchone()["current_sequence"])

            # 2. Derive unique idempotency key
            idempotency_key = f"volunteer:{self.device_id}:{seq}"
            created_at_iso = draft.client_created_at.isoformat()

            # 3. Store offline report
            conn.execute(
                """
                INSERT INTO offline_reports (
                    id, device_id, sequence, disaster_id, source_identity, language_code,
                    client_created_at, raw_payload, idempotency_key, sync_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(report_id),
                    str(self.device_id),
                    seq,
                    str(draft.disaster_id),
                    draft.source_identity,
                    draft.language_code,
                    created_at_iso,
                    json.dumps(draft.raw_payload, sort_keys=True),
                    idempotency_key,
                    SyncStatus.LOCALLY_SAVED.value,
                ),
            )

        return OfflineReport(
            id=report_id,
            device_id=self.device_id,
            sequence=seq,
            disaster_id=draft.disaster_id,
            raw_payload=draft.raw_payload,
            source_identity=draft.source_identity,
            language_code=draft.language_code,
            client_created_at=draft.client_created_at,
            idempotency_key=idempotency_key,
            sync_status=SyncStatus.LOCALLY_SAVED,
        )

    def create_sync_batch(self, limit: int = 50) -> Optional[SyncBatch]:
        """Claim a batch of pending offline reports and transition them to 'syncing' status."""
        batch_id = uuid.uuid4()

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM offline_reports
                WHERE sync_status IN (?, ?)
                ORDER BY sequence ASC
                LIMIT ?;
                """,
                (SyncStatus.LOCALLY_SAVED.value, SyncStatus.FAILED.value, limit),
            )
            rows = cursor.fetchall()
            if not rows:
                return None

            report_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in report_ids)

            conn.execute(
                f"""
                UPDATE offline_reports
                SET sync_status = ?, batch_id = ?
                WHERE id IN ({placeholders});
                """,
                (SyncStatus.SYNCING.value, str(batch_id), *report_ids),
            )

        items = [
            SyncReportItem(
                event_id=uuid.UUID(row["id"]),
                sequence=row["sequence"],
                disaster_id=uuid.UUID(row["disaster_id"]),
                raw_payload=json.loads(row["raw_payload"]),
                client_created_at=datetime.fromisoformat(row["client_created_at"]),
                idempotency_key=row["idempotency_key"],
                source_identity=row["source_identity"],
                language_code=row["language_code"],
            )
            for row in rows
        ]

        return SyncBatch(
            device_id=self.device_id,
            batch_id=batch_id,
            from_sequence=items[0].sequence,
            to_sequence=items[-1].sequence,
            items=items,
        )

    def acknowledge_batch(self, ack: SyncAck) -> int:
        """Mark reports acknowledged by the server as 'server_synchronized'."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE offline_reports
                SET sync_status = ?,
                    synced_at = ?,
                    error_message = NULL
                WHERE device_id = ?
                  AND batch_id = ?
                  AND sequence <= ?
                  AND sync_status = ?;
                """,
                (
                    SyncStatus.SERVER_SYNCHRONIZED.value,
                    ack.server_synced_at.isoformat(),
                    str(self.device_id),
                    str(ack.batch_id),
                    ack.acknowledged_sequence,
                    SyncStatus.SYNCING.value,
                ),
            )
            return cursor.rowcount

    def fail_batch(self, batch_id: uuid.UUID, error_message: str) -> int:
        """Reset reports in an in-flight batch back to 'failed' on network or server error."""
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE offline_reports
                SET sync_status = ?,
                    error_message = ?
                WHERE device_id = ?
                  AND batch_id = ?
                  AND sync_status = ?;
                """,
                (
                    SyncStatus.FAILED.value,
                    error_message,
                    str(self.device_id),
                    str(batch_id),
                    SyncStatus.SYNCING.value,
                ),
            )
            return cursor.rowcount

    def get_report(self, report_id: uuid.UUID) -> Optional[OfflineReport]:
        """Fetch an individual offline report by its UUID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM offline_reports WHERE id = ?;",
                (str(report_id),),
            )
            row = cursor.fetchone()
            return _row_to_report(row) if row else None

    def list_reports(
        self,
        status: Optional[SyncStatus] = None,
    ) -> list[OfflineReport]:
        """List reports in sequence order, optionally filtered by SyncStatus."""
        with self.db.connection() as conn:
            if status is not None:
                cursor = conn.execute(
                    """
                    SELECT * FROM offline_reports
                    WHERE sync_status = ?
                    ORDER BY sequence ASC;
                    """,
                    (status.value,),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM offline_reports ORDER BY sequence ASC;"
                )
            return [_row_to_report(row) for row in cursor.fetchall()]

    def get_sync_counts(self) -> dict[str, int]:
        """Return counts of reports grouped by their synchronization status."""
        counts = {status.value: 0 for status in SyncStatus}
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT sync_status, count(*) as cnt FROM offline_reports GROUP BY sync_status;"
            )
            for row in cursor.fetchall():
                counts[row["sync_status"]] = int(row["cnt"])
        return counts

