"""Device synchronization API routes for offline field app."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from field_app.models import SyncAck, SyncBatch
from raahat.adapters.channels.volunteer.service import DeviceSyncService
from raahat.api.dependencies import get_device_sync_service, require_device_id
from raahat.application.ingestion.service import DisasterNotFoundError

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceCursorResponse(BaseModel):
    """Current synchronization cursor state for a field device."""

    device_id: uuid.UUID
    last_sequence: int
    last_synced_at: str
    sync_metadata: dict[str, Any]


@router.post(
    "/sync",
    response_model=SyncAck,
    status_code=status.HTTP_200_OK,
    summary="Synchronize a batch of offline field reports",
)
def sync_device_batch(
    batch: SyncBatch,
    authenticated_device_id: uuid.UUID = Depends(require_device_id),
    sync_service: DeviceSyncService = Depends(get_device_sync_service),
) -> SyncAck:
    """Ingest a batch of offline reports drafted by field volunteers.

    Requires authenticated device UUID in the X-Device-Id header matching batch.device_id.
    Guarantees 100% idempotent handling of duplicate and retransmitted batches.
    Advances device sync cursor in sync_cursors and publishes outbox events atomically.
    """
    if authenticated_device_id != batch.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated device ID does not match batch payload",
        )

    try:
        return sync_service.sync_batch(
            authenticated_device_id=authenticated_device_id,
            batch=batch,
        )
    except DisasterNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/{device_id}/cursor",
    response_model=DeviceCursorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current sync cursor for a field device",
)
def get_device_cursor(
    device_id: uuid.UUID,
    sync_service: DeviceSyncService = Depends(get_device_sync_service),
) -> DeviceCursorResponse:
    """Retrieve the latest synchronization cursor and sequence position for a device."""
    cursor_info = sync_service.get_device_cursor(device_id)
    if cursor_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sync cursor found for device '{device_id}'",
        )
    return DeviceCursorResponse(
        device_id=uuid.UUID(str(cursor_info["device_id"])),
        last_sequence=int(cursor_info["last_sequence"]),
        last_synced_at=str(cursor_info["last_synced_at"]),
        sync_metadata=dict(cursor_info["sync_metadata"]),
    )
