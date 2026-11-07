"""Background worker monitoring device synchronization health and sequence continuity."""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Optional

from sqlalchemy import select

from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.report import ReportModel
from raahat.infrastructure.database.models.sync import SyncCursorModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncWorkerConfig:
    """Configuration for device sync monitor worker."""

    poll_interval_s: float = 1.0
    stale_device_threshold_s: float = 3600.0  # 1 hour default


class SyncWorker:
    """Worker monitoring device cursors for stale connections and sequence continuity gaps."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        config: SyncWorkerConfig = SyncWorkerConfig(),
    ) -> None:
        self._session_factory = session_factory
        self._config = config

    def find_stale_devices(
        self,
        threshold_seconds: Optional[float] = None,
    ) -> list[uuid.UUID]:
        """Find devices whose last synchronization timestamp exceeds the staleness threshold."""
        threshold = threshold_seconds or self._config.stale_device_threshold_s
        cutoff = utc_now() - timedelta(seconds=threshold)

        with self._session_factory() as session:
            stmt = select(SyncCursorModel.device_id).where(
                SyncCursorModel.last_synced_at < cutoff
            )
            return list(session.execute(stmt).scalars().all())

    def audit_device_sequences(self, device_id: uuid.UUID) -> dict[str, Any]:
        """Inspect reports for a device and verify gapless monotonic sequence continuity."""
        with self._session_factory() as session:
            cursor = (
                session.query(SyncCursorModel)
                .filter_by(device_id=device_id)
                .first()
            )
            if not cursor:
                return {
                    "device_id": str(device_id),
                    "found": False,
                    "error": "No sync cursor found for device",
                }

            # Retrieve all channel_reference values for this device to extract sequences
            stmt = select(ReportModel.channel_reference).where(
                ReportModel.device_id == device_id
            )
            refs = session.execute(stmt).scalars().all()

        found_sequences: set[int] = set()
        seq_pattern = re.compile(r"seq:(\d+)")
        for ref in refs:
            if ref:
                match = seq_pattern.search(ref)
                if match:
                    found_sequences.add(int(match.group(1)))

        expected_sequences = set(range(1, cursor.last_sequence + 1))
        missing_sequences = sorted(expected_sequences - found_sequences)

        return {
            "device_id": str(device_id),
            "found": True,
            "last_sequence": cursor.last_sequence,
            "last_synced_at": cursor.last_synced_at.isoformat(),
            "received_count": len(found_sequences),
            "missing_sequences": missing_sequences,
            "is_continuous": len(missing_sequences) == 0,
        }

    def run_audit_tick(
        self,
        stale_threshold_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        """Run a single audit evaluation pass across all registered devices."""
        stale_devices = self.find_stale_devices(stale_threshold_seconds)

        devices_with_gaps: list[dict[str, Any]] = []
        with self._session_factory() as session:
            all_device_ids = list(
                session.execute(select(SyncCursorModel.device_id)).scalars().all()
            )

        for dev_id in all_device_ids:
            audit = self.audit_device_sequences(dev_id)
            if not audit.get("is_continuous", True):
                devices_with_gaps.append(audit)

        return {
            "timestamp": utc_now().isoformat(),
            "total_devices": len(all_device_ids),
            "stale_device_count": len(stale_devices),
            "stale_devices": [str(d) for d in stale_devices],
            "gap_count": len(devices_with_gaps),
            "devices_with_gaps": devices_with_gaps,
        }
