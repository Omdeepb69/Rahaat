"""Assignment, operation event and dispatch decision database models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class AssignmentModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("assignments_incident_idx", "incident_id", "created_at"),
        Index("assignments_status_idx", "status", "created_at"),
        # A resource can be committed to one incident at a time. Enforced by
        # the database so two dispatchers cannot both commit the same unit.
        Index(
            "assignments_one_active_per_resource",
            "resource_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # proposed | approved | rejected | completed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    # Latest field milestone while approved: approved | acknowledged | en_route | on_scene | rescued | closed
    stage: Mapped[str] = mapped_column(String(32), default="proposed", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    incident = relationship("IncidentModel")
    resource = relationship("ResourceModel")
    events = relationship("OperationEventModel", back_populates="assignment")


class OperationEventModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "operation_events"
    __table_args__ = (Index("operation_events_assignment_idx", "assignment_id", "created_at"),)

    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    assignment = relationship("AssignmentModel", back_populates="events")
    incident = relationship("IncidentModel")


class DispatchDecisionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A human decision on committing a resource to an incident.

    Stores what the engine recommended at the moment of the decision, what the
    person chose, and their stated reason, so the two can always be compared.
    """

    __tablename__ = "dispatch_decisions"
    __table_args__ = (
        Index("dispatch_decisions_incident_idx", "incident_id", "created_at"),
        CheckConstraint(
            "decision IN ('approved','rejected')", name="dispatch_decisions_decision_valid"
        ),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    chosen_resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    recommended_resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    followed_recommendation: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    recommendation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
