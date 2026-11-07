"""PostgreSQL implementation of AssignmentRepository."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.operations.operation import Assignment, OperationEvent
from raahat.domain.operations.repository import AssignmentRepository
from raahat.domain.shared.enums import AssignmentStatus, OperationEventType
from raahat.infrastructure.database.models.operation import AssignmentModel, OperationEventModel


def _model_to_assignment(model: AssignmentModel) -> Assignment:
    return Assignment(
        id=model.id,
        incident_id=model.incident_id,
        resource_id=model.resource_id,
        assigned_by=model.assigned_by,
        status=AssignmentStatus(model.status),
        approved_at=model.approved_at,
        created_at=model.created_at,
    )


def _model_to_event(model: OperationEventModel) -> OperationEvent:
    return OperationEvent(
        id=model.id,
        assignment_id=model.assignment_id,
        incident_id=model.incident_id,
        event_type=OperationEventType(model.event_type),
        actor_id=model.actor_id,
        notes=model.notes,
        payload=dict(model.payload) if model.payload else {},
        created_at=model.created_at,
    )


class PostgresAssignmentRepository(AssignmentRepository):
    """PostgreSQL-backed repository for assignments and operation events."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, assignment: Assignment) -> Assignment:
        with self._session_factory() as session:
            model = AssignmentModel(
                id=assignment.id,
                incident_id=assignment.incident_id,
                resource_id=assignment.resource_id,
                assigned_by=assignment.assigned_by,
                status=assignment.status.value,
                approved_at=assignment.approved_at,
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _model_to_assignment(model)

    def get_by_id(self, assignment_id: uuid.UUID) -> Optional[Assignment]:
        with self._session_factory() as session:
            model = session.get(AssignmentModel, assignment_id)
            return _model_to_assignment(model) if model is not None else None

    def list_by_incident(self, incident_id: uuid.UUID) -> list[Assignment]:
        with self._session_factory() as session:
            stmt = (
                select(AssignmentModel)
                .where(AssignmentModel.incident_id == incident_id)
                .order_by(AssignmentModel.created_at.desc())
            )
            models = session.scalars(stmt).all()
            return [_model_to_assignment(m) for m in models]

    def update_status(
        self,
        assignment_id: uuid.UUID,
        status: AssignmentStatus,
        approved_at: Optional[datetime] = None,
    ) -> Optional[Assignment]:
        with self._session_factory() as session:
            model = session.get(AssignmentModel, assignment_id)
            if model is None:
                return None
            model.status = status.value
            if approved_at is not None:
                model.approved_at = approved_at
            session.commit()
            session.refresh(model)
            return _model_to_assignment(model)

    def save_event(self, event: OperationEvent) -> OperationEvent:
        with self._session_factory() as session:
            model = OperationEventModel(
                id=event.id,
                assignment_id=event.assignment_id,
                incident_id=event.incident_id,
                event_type=event.event_type.value,
                actor_id=event.actor_id,
                notes=event.notes,
                payload=dict(event.payload),
            )
            session.add(model)
            session.commit()
            session.refresh(model)
            return _model_to_event(model)

    def list_events(self, assignment_id: uuid.UUID) -> list[OperationEvent]:
        with self._session_factory() as session:
            stmt = (
                select(OperationEventModel)
                .where(OperationEventModel.assignment_id == assignment_id)
                .order_by(OperationEventModel.created_at.asc())
            )
            models = session.scalars(stmt).all()
            return [_model_to_event(m) for m in models]

