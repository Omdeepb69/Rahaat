"""PostgreSQL-backed EvidenceRepository implementation."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from raahat.domain.evidence.evidence import EvidenceItem, EvidenceSpan
from raahat.domain.evidence.repository import EvidenceRepository, InMemoryEvidenceRepository
from raahat.domain.shared.enums import VerificationStatus
from raahat.infrastructure.database.models.evidence import (
    EvidenceItemModel,
    EvidenceSpanModel,
)


def model_to_evidence_item(model: EvidenceItemModel) -> EvidenceItem:
    """Convert an EvidenceItemModel database record to a domain EvidenceItem."""
    spans = tuple(
        EvidenceSpan(
            id=s.id,
            start_ms=s.source_start_ms,
            end_ms=s.source_end_ms,
            text=s.source_text,
            reference=dict(s.source_reference or {}),
        )
        for s in model.spans
    )
    return EvidenceItem(
        id=model.id,
        report_id=model.report_id,
        subject_type=model.subject_type,
        subject_id=model.subject_id,
        attribute=model.attribute,
        value=model.value,
        confidence=model.confidence,
        verification_status=VerificationStatus(model.verification_status),
        observed_at=model.observed_at,
        spans=spans,
    )


def evidence_item_to_model(item: EvidenceItem) -> EvidenceItemModel:
    """Convert a domain EvidenceItem to an EvidenceItemModel database record with spans."""
    model = EvidenceItemModel(
        id=item.id,
        report_id=item.report_id,
        subject_type=item.subject_type,
        subject_id=item.subject_id,
        attribute=item.attribute,
        value=item.value,
        confidence=item.confidence,
        verification_status=item.verification_status.value,
        observed_at=item.observed_at,
    )
    for s in item.spans:
        span_model = EvidenceSpanModel(
            id=s.id,
            evidence_id=item.id,
            source_start_ms=s.start_ms,
            source_end_ms=s.end_ms,
            source_text=s.text,
            source_reference=dict(s.reference or {}),
        )
        model.spans.append(span_model)
    return model


class PostgresEvidenceRepository:
    """PostgreSQL implementation of EvidenceRepository using SQLAlchemy."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(
        self,
        item: EvidenceItem,
        session: Optional[Session] = None,
    ) -> EvidenceItem:
        if session is not None:
            return self._save_internal(session, item)

        with self._session_factory() as managed_session:
            saved = self._save_internal(managed_session, item)
            managed_session.commit()
            return saved

    def save_all(
        self,
        items: list[EvidenceItem],
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        if not items:
            return []

        if session is not None:
            return self._save_all_internal(session, items)

        with self._session_factory() as managed_session:
            saved = self._save_all_internal(managed_session, items)
            managed_session.commit()
            return saved

    def get_by_id(
        self,
        item_id: uuid.UUID,
        session: Optional[Session] = None,
    ) -> Optional[EvidenceItem]:
        if session is not None:
            return self._get_by_id_internal(session, item_id)

        with self._session_factory() as managed_session:
            return self._get_by_id_internal(managed_session, item_id)

    def list_by_report_id(
        self,
        report_id: uuid.UUID,
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        return self.list_by_report_ids([report_id], session=session)

    def list_by_report_ids(
        self,
        report_ids: list[uuid.UUID],
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        if not report_ids:
            return []

        if session is not None:
            return self._list_by_report_ids_internal(session, report_ids)

        with self._session_factory() as managed_session:
            return self._list_by_report_ids_internal(managed_session, report_ids)

    def list_by_subject(
        self,
        subject_type: str,
        subject_id: Optional[uuid.UUID] = None,
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        if session is not None:
            return self._list_by_subject_internal(session, subject_type, subject_id)

        with self._session_factory() as managed_session:
            return self._list_by_subject_internal(managed_session, subject_type, subject_id)

    def list_by_attribute(
        self,
        attribute: str,
        session: Optional[Session] = None,
    ) -> list[EvidenceItem]:
        if session is not None:
            return self._list_by_attribute_internal(session, attribute)

        with self._session_factory() as managed_session:
            return self._list_by_attribute_internal(managed_session, attribute)

    def _save_internal(self, session: Session, item: EvidenceItem) -> EvidenceItem:
        model = evidence_item_to_model(item)
        session.merge(model)
        session.flush()
        return model_to_evidence_item(model)

    def _save_all_internal(self, session: Session, items: list[EvidenceItem]) -> list[EvidenceItem]:
        models = [evidence_item_to_model(it) for it in items]
        for m in models:
            session.merge(m)
        session.flush()
        return [model_to_evidence_item(m) for m in models]

    def _get_by_id_internal(self, session: Session, item_id: uuid.UUID) -> Optional[EvidenceItem]:
        stmt = (
            select(EvidenceItemModel)
            .where(EvidenceItemModel.id == item_id)
            .options(selectinload(EvidenceItemModel.spans))
        )
        model = session.execute(stmt).scalar_one_or_none()
        return model_to_evidence_item(model) if model else None

    def _list_by_report_ids_internal(
        self,
        session: Session,
        report_ids: list[uuid.UUID],
    ) -> list[EvidenceItem]:
        stmt = (
            select(EvidenceItemModel)
            .where(EvidenceItemModel.report_id.in_(report_ids))
            .options(selectinload(EvidenceItemModel.spans))
            .order_by(EvidenceItemModel.created_at.asc())
        )
        models = session.execute(stmt).scalars().all()
        return [model_to_evidence_item(m) for m in models]

    def _list_by_subject_internal(
        self,
        session: Session,
        subject_type: str,
        subject_id: Optional[uuid.UUID],
    ) -> list[EvidenceItem]:
        stmt = (
            select(EvidenceItemModel)
            .where(EvidenceItemModel.subject_type == subject_type)
            .options(selectinload(EvidenceItemModel.spans))
        )
        if subject_id is not None:
            stmt = stmt.where(EvidenceItemModel.subject_id == subject_id)
        stmt = stmt.order_by(EvidenceItemModel.created_at.asc())
        models = session.execute(stmt).scalars().all()
        return [model_to_evidence_item(m) for m in models]

    def _list_by_attribute_internal(
        self,
        session: Session,
        attribute: str,
    ) -> list[EvidenceItem]:
        stmt = (
            select(EvidenceItemModel)
            .where(EvidenceItemModel.attribute == attribute)
            .options(selectinload(EvidenceItemModel.spans))
            .order_by(EvidenceItemModel.created_at.asc())
        )
        models = session.execute(stmt).scalars().all()
        return [model_to_evidence_item(m) for m in models]


__all__ = [
    "EvidenceRepository",
    "InMemoryEvidenceRepository",
    "PostgresEvidenceRepository",
    "evidence_item_to_model",
    "model_to_evidence_item",
]
