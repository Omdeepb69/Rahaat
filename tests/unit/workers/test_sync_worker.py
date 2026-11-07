"""Unit tests for SyncWorker device monitoring and continuity audit."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from raahat.workers.sync_worker import SyncWorker, SyncWorkerConfig


class FakeCursor:
    def __init__(
        self,
        device_id: uuid.UUID,
        last_sequence: int,
        last_synced_at: datetime,
    ) -> None:
        self.device_id = device_id
        self.last_sequence = last_sequence
        self.last_synced_at = last_synced_at


class FakeSession:
    def __init__(
        self,
        cursors: list[FakeCursor],
        channel_refs: dict[uuid.UUID, list[str]],
    ) -> None:
        self.cursors = cursors
        self.channel_refs = channel_refs

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def query(self, model_cls: type) -> Any:
        class QueryProxy:
            def __init__(proxy_self, items: list) -> None:
                proxy_self.items = items

            def filter_by(proxy_self, **kwargs: Any) -> Any:
                filtered = [
                    it
                    for it in proxy_self.items
                    if all(getattr(it, k) == v for k, v in kwargs.items())
                ]
                class FilterProxy:
                    def first(self) -> Any:
                        return filtered[0] if filtered else None
                return FilterProxy()

        return QueryProxy(self.cursors)

    def execute(self, stmt: Any) -> Any:
        class ResultProxy:
            def __init__(proxy_self, data: list) -> None:
                proxy_self._data = data

            def scalars(proxy_self) -> Any:
                class ScalarProxy:
                    def all(self) -> list:
                        return proxy_self._data
                return ScalarProxy()

        # If selecting device_id from cursors
        sql_str = str(stmt).lower()
        if "sync_cursors.last_synced_at <" in sql_str:
            # Stale check
            cutoff = stmt.compile().params.get("last_synced_at_1")
            stale = [
                c.device_id
                for c in self.cursors
                if cutoff is None or c.last_synced_at < cutoff
            ]
            return ResultProxy(stale)

        if "sync_cursors.device_id" in sql_str:
            return ResultProxy([c.device_id for c in self.cursors])

        if "reports.channel_reference" in sql_str:
            params = stmt.compile().params
            dev_id = params.get("device_id_1")
            return ResultProxy(self.channel_refs.get(dev_id, []))

        return ResultProxy([])


def test_find_stale_devices() -> None:
    now = datetime.now(timezone.utc)
    dev_fresh = uuid.uuid4()
    dev_stale = uuid.uuid4()

    cursors = [
        FakeCursor(device_id=dev_fresh, last_sequence=5, last_synced_at=now - timedelta(minutes=10)),
        FakeCursor(device_id=dev_stale, last_sequence=2, last_synced_at=now - timedelta(hours=3)),
    ]
    session_factory = lambda: FakeSession(cursors=cursors, channel_refs={})  # noqa: E731

    worker = SyncWorker(session_factory, SyncWorkerConfig(stale_device_threshold_s=3600.0))  # 1 hour
    stale_ids = worker.find_stale_devices()

    assert dev_stale in stale_ids
    assert dev_fresh not in stale_ids


def test_audit_device_sequences_detects_continuity_and_gaps() -> None:
    now = datetime.now(timezone.utc)
    dev_continuous = uuid.uuid4()
    dev_with_gap = uuid.uuid4()

    cursors = [
        FakeCursor(device_id=dev_continuous, last_sequence=3, last_synced_at=now),
        FakeCursor(device_id=dev_with_gap, last_sequence=4, last_synced_at=now),
    ]
    channel_refs = {
        # Continuous: seq 1, 2, 3
        dev_continuous: ["batch:b1:seq:1", "batch:b1:seq:2", "batch:b1:seq:3"],
        # Gap: seq 1, 2, 4 (missing seq 3)
        dev_with_gap: ["batch:b2:seq:1", "batch:b2:seq:2", "batch:b2:seq:4"],
    }
    session_factory = lambda: FakeSession(cursors=cursors, channel_refs=channel_refs)  # noqa: E731

    worker = SyncWorker(session_factory)

    audit_ok = worker.audit_device_sequences(dev_continuous)
    assert audit_ok["is_continuous"] is True
    assert audit_ok["missing_sequences"] == []
    assert audit_ok["received_count"] == 3

    audit_gap = worker.audit_device_sequences(dev_with_gap)
    assert audit_gap["is_continuous"] is False
    assert audit_gap["missing_sequences"] == [3]
    assert audit_gap["received_count"] == 3
