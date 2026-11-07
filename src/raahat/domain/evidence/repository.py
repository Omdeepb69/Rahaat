"""EvidenceRepository protocol and pure-Python in-memory implementation."""
from __future__ import annotations

import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from raahat.domain.evidence.evidence import EvidenceItem


@runtime_checkable
class EvidenceRepository(Protocol):
    """Protocol for persisting and retrieving decomposed evidence items and spans."""

    def save(
        self,
        item: EvidenceItem,
        session: Optional[Any] = None,
    ) -> EvidenceItem:
        """Persist a single evidence item with its spans."""
        ...

    def save_all(
        self,
        items: list[EvidenceItem],
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        """Persist multiple evidence items in a single transaction."""
        ...

    def get_by_id(
        self,
        item_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[EvidenceItem]:
        """Retrieve an evidence item by its primary key."""
        ...

    def list_by_report_id(
        self,
        report_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        """List all evidence items extracted from a given report."""
        ...

    def list_by_report_ids(
        self,
        report_ids: list[uuid.UUID],
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        """List all evidence items extracted across multiple reports."""
        ...

    def list_by_subject(
        self,
        subject_type: str,
        subject_id: Optional[uuid.UUID] = None,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        """List all evidence items pertaining to a subject type and optional subject ID."""
        ...

    def list_by_attribute(
        self,
        attribute: str,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        """List all evidence items matching an attribute name."""
        ...


class InMemoryEvidenceRepository:
    """Pure-Python in-memory evidence repository for unit tests and isolated evaluation."""

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, EvidenceItem] = {}

    def save(
        self,
        item: EvidenceItem,
        session: Optional[Any] = None,
    ) -> EvidenceItem:
        self._items[item.id] = item
        return item

    def save_all(
        self,
        items: list[EvidenceItem],
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        for it in items:
            self._items[it.id] = it
        return items

    def get_by_id(
        self,
        item_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[EvidenceItem]:
        return self._items.get(item_id)

    def list_by_report_id(
        self,
        report_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        return [it for it in self._items.values() if it.report_id == report_id]

    def list_by_report_ids(
        self,
        report_ids: list[uuid.UUID],
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        id_set = set(report_ids)
        return [it for it in self._items.values() if it.report_id in id_set]

    def list_by_subject(
        self,
        subject_type: str,
        subject_id: Optional[uuid.UUID] = None,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        return [
            it
            for it in self._items.values()
            if it.subject_type == subject_type
            and (subject_id is None or it.subject_id == subject_id)
        ]

    def list_by_attribute(
        self,
        attribute: str,
        session: Optional[Any] = None,
    ) -> list[EvidenceItem]:
        return [it for it in self._items.values() if it.attribute == attribute]

