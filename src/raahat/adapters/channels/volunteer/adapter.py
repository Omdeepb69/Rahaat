"""Volunteer channel adapter for offline field app report items."""
from __future__ import annotations

import uuid
from typing import Optional

from field_app.models import SyncReportItem
from raahat.domain.reports.report import ReportSubmission
from raahat.domain.shared.enums import SourceType


class VolunteerSyncAdapter:
    """Transforms offline field app sync items into normalized ReportSubmissions."""

    @staticmethod
    def to_submission(
        device_id: uuid.UUID,
        item: SyncReportItem,
        batch_id: Optional[uuid.UUID] = None,
    ) -> ReportSubmission:
        """Convert a SyncReportItem into a domain ReportSubmission with preserved client timestamp."""
        channel_ref = (
            f"batch:{batch_id}:seq:{item.sequence}"
            if batch_id is not None
            else f"seq:{item.sequence}"
        )
        idempotency_key = (
            item.idempotency_key
            if item.idempotency_key
            else f"volunteer:{device_id}:{item.sequence}"
        )

        return ReportSubmission(
            disaster_id=item.disaster_id,
            source_type=SourceType.VOLUNTEER,
            source_identity=item.source_identity,
            source_event_id=str(item.event_id),
            device_id=device_id,
            channel_reference=channel_ref,
            raw_payload=item.raw_payload,
            client_created_at=item.client_created_at,  # Preserved distinctly from server receipt
            language_code=item.language_code,
            idempotency_key=idempotency_key,
        )
