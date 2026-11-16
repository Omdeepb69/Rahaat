"""Incident review service handling dispatcher verification, merge approvals, and reversible unmerge."""
from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.shared.enums import (
    IncidentLinkType,
    IncidentStatus,
    RelationshipType,
)
from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.incident import (
    IncidentLinkModel,
    IncidentModel,
    IncidentReportModel,
)
from raahat.infrastructure.database.models.merge import EntityMergeEventModel
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    PostgresAuditRepository,
)

logger = logging.getLogger(__name__)


class LinkReviewAction(str, Enum):
    """Actions dispatcher can execute when reviewing incident candidate relationships."""

    APPROVE_MERGE = "approve_merge"
    REJECT_MERGE = "reject_merge"
    RELATE_CLUSTER = "relate_cluster"
    UNMERGE = "unmerge"


class MergeActionResult(BaseModel):
    """Outcome of merge approval, rejection, or unmerge reversibility."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    merge_event_id: Optional[uuid.UUID] = None
    source_incident_id: uuid.UUID
    target_incident_id: uuid.UUID
    status: str
    action: str
    audit_event_id: uuid.UUID
    reassigned_report_count: int = 0


class IncidentReviewService:
    """Service orchestrating human dispatcher verification, merge decisions, and reversible linking."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        audit_repo: Optional[AuditRepository] = None,
    ) -> None:
        self.session_factory = session_factory
        self.audit_repo = audit_repo or PostgresAuditRepository(session_factory)

    def review_link(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        action: LinkReviewAction,
        dispatcher_id: uuid.UUID,
        reason: str,
        merge_event_id: Optional[uuid.UUID] = None,
        session: Optional[Session] = None,
    ) -> MergeActionResult:
        """Execute a merge review decision (approve, reject, relate cluster, unmerge)."""
        if session is not None:
            return self._review_link_impl(
                source_incident_id, target_incident_id, action, dispatcher_id, reason, merge_event_id, session
            )
        with self.session_factory() as new_session:
            res = self._review_link_impl(
                source_incident_id, target_incident_id, action, dispatcher_id, reason, merge_event_id, new_session
            )
            new_session.commit()
            return res

    def _review_link_impl(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        action: LinkReviewAction,
        dispatcher_id: uuid.UUID,
        reason: str,
        merge_event_id: Optional[uuid.UUID],
        session: Session,
    ) -> MergeActionResult:
        if action == LinkReviewAction.APPROVE_MERGE:
            return self._approve_merge(source_incident_id, target_incident_id, dispatcher_id, reason, session)
        elif action == LinkReviewAction.REJECT_MERGE:
            return self._reject_merge(source_incident_id, target_incident_id, dispatcher_id, reason, session)
        elif action == LinkReviewAction.RELATE_CLUSTER:
            return self._relate_cluster(source_incident_id, target_incident_id, dispatcher_id, reason, session)
        elif action == LinkReviewAction.UNMERGE:
            return self._unmerge(source_incident_id, target_incident_id, dispatcher_id, reason, merge_event_id, session)
        else:
            raise ValueError(f"Unsupported review action: {action}")

    def _approve_merge(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        reason: str,
        session: Session,
    ) -> MergeActionResult:
        if source_incident_id == target_incident_id:
            raise ValueError("Cannot merge an incident into itself")

        source_inc = session.get(IncidentModel, source_incident_id)
        if not source_inc:
            raise KeyError(f"Source incident {source_incident_id} not found")

        target_inc = session.get(IncidentModel, target_incident_id)
        if not target_inc:
            raise KeyError(f"Target incident {target_incident_id} not found")
        if source_inc.disaster_id != target_inc.disaster_id:
            raise ValueError("Incidents belong to different operations and cannot be merged")
        if source_inc.status == IncidentStatus.DUPLICATE.value:
            raise ValueError("The source incident has already been merged into another incident")
        if target_inc.status in (IncidentStatus.DUPLICATE.value, IncidentStatus.CLOSED.value):
            raise ValueError("The target incident is closed or is itself a duplicate")
        if source_inc.status in (IncidentStatus.ASSIGNED.value, IncidentStatus.IN_PROGRESS.value):
            raise ValueError(
                "The source incident has resources committed. Merge into it instead, "
                "or complete its assignments first."
            )

        # 1. Record entity merge event
        merge_event_id = uuid.uuid4()
        merge_event = EntityMergeEventModel(
            id=merge_event_id,
            source_entity_type="incident",
            source_entity_id=source_incident_id,
            target_entity_type="incident",
            target_entity_id=target_incident_id,
            reviewed_by=dispatcher_id,
            reason=reason,
            status="active",
        )
        session.add(merge_event)

        # 2. Reassign source reports as corroborating on target incident without deleting original links
        source_reports = session.scalars(
            select(IncidentReportModel).where(IncidentReportModel.incident_id == source_incident_id)
        ).all()

        reassigned_count = 0
        for s_rep in source_reports:
            exists = session.scalar(
                select(IncidentReportModel).where(
                    IncidentReportModel.incident_id == target_incident_id,
                    IncidentReportModel.report_id == s_rep.report_id,
                )
            )
            if not exists:
                new_link = IncidentReportModel(
                    incident_id=target_incident_id,
                    report_id=s_rep.report_id,
                    relationship=RelationshipType.CORROBORATING.value,
                    linked_by=f"merge:{merge_event.id}",
                    reviewed_by=dispatcher_id,
                )
                session.add(new_link)
                reassigned_count += 1

        # 3. Mark the source as a duplicate of the target, remembering where it was.
        facts = dict(source_inc.severity_facts or {})
        facts["merged_into"] = str(target_incident_id)
        facts["merge_event_id"] = str(merge_event.id)
        facts["status_before_merge"] = source_inc.status
        source_inc.severity_facts = facts
        source_inc.status = IncidentStatus.DUPLICATE.value
        source_inc.merged_into_id = target_incident_id

        # 4. Update or create incident link
        link_stmt = select(IncidentLinkModel).where(
            ((IncidentLinkModel.incident_a_id == source_incident_id) & (IncidentLinkModel.incident_b_id == target_incident_id))
            | ((IncidentLinkModel.incident_a_id == target_incident_id) & (IncidentLinkModel.incident_b_id == source_incident_id))
        )
        inc_link = session.scalars(link_stmt).first()
        if inc_link:
            inc_link.status = "approved"
            inc_link.reviewed_by = dispatcher_id
            inc_link.reviewed_at = utc_now()
            inc_link.review_reason = reason
        else:
            inc_link = IncidentLinkModel(
                id=uuid.uuid4(),
                incident_a_id=source_incident_id,
                incident_b_id=target_incident_id,
                link_type=IncidentLinkType.POSSIBLE_DUPLICATE.value,
                confidence=1.0,
                status="approved",
            )
            session.add(inc_link)

        session.flush()

        audit_event = self.audit_repo.record_event(
            session=session,
            action="incident.merge_approved",
            actor_id=dispatcher_id,
            entity_type="incident",
            entity_id=target_incident_id,
            payload={
                "source_incident_id": str(source_incident_id),
                "target_incident_id": str(target_incident_id),
                "merge_event_id": str(merge_event_id),
                "reason": reason,
                "reassigned_report_count": reassigned_count,
            },
        )

        logger.info(
            "Incident %s merged into %s by dispatcher %s (event: %s)",
            source_incident_id,
            target_incident_id,
            dispatcher_id,
            merge_event_id,
        )

        return MergeActionResult(
            merge_event_id=merge_event_id,
            source_incident_id=source_incident_id,
            target_incident_id=target_incident_id,
            status="active",
            action="approved",
            audit_event_id=audit_event.id,
            reassigned_report_count=reassigned_count,
        )

    def _reject_merge(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        reason: str,
        session: Session,
    ) -> MergeActionResult:
        link_stmt = select(IncidentLinkModel).where(
            ((IncidentLinkModel.incident_a_id == source_incident_id) & (IncidentLinkModel.incident_b_id == target_incident_id))
            | ((IncidentLinkModel.incident_a_id == target_incident_id) & (IncidentLinkModel.incident_b_id == source_incident_id))
        )
        inc_link = session.scalars(link_stmt).first()
        if inc_link:
            inc_link.status = "rejected"
            inc_link.reviewed_by = dispatcher_id
            inc_link.reviewed_at = utc_now()
            inc_link.review_reason = reason
        else:
            inc_link = IncidentLinkModel(
                id=uuid.uuid4(),
                incident_a_id=source_incident_id,
                incident_b_id=target_incident_id,
                link_type=IncidentLinkType.POSSIBLE_DUPLICATE.value,
                confidence=0.0,
                status="rejected",
            )
            session.add(inc_link)

        session.flush()

        audit_event = self.audit_repo.record_event(
            session=session,
            action="incident.merge_rejected",
            actor_id=dispatcher_id,
            entity_type="incident",
            entity_id=target_incident_id,
            payload={
                "source_incident_id": str(source_incident_id),
                "target_incident_id": str(target_incident_id),
                "reason": reason,
            },
        )

        return MergeActionResult(
            merge_event_id=None,
            source_incident_id=source_incident_id,
            target_incident_id=target_incident_id,
            status="rejected",
            action="rejected",
            audit_event_id=audit_event.id,
            reassigned_report_count=0,
        )

    def _relate_cluster(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        reason: str,
        session: Session,
    ) -> MergeActionResult:
        link_stmt = select(IncidentLinkModel).where(
            ((IncidentLinkModel.incident_a_id == source_incident_id) & (IncidentLinkModel.incident_b_id == target_incident_id))
            | ((IncidentLinkModel.incident_a_id == target_incident_id) & (IncidentLinkModel.incident_b_id == source_incident_id))
        )
        inc_link = session.scalars(link_stmt).first()
        if inc_link:
            inc_link.link_type = IncidentLinkType.RELATED_CLUSTER.value
            inc_link.status = "approved"
            inc_link.reviewed_by = dispatcher_id
            inc_link.reviewed_at = utc_now()
            inc_link.review_reason = reason
        else:
            inc_link = IncidentLinkModel(
                id=uuid.uuid4(),
                incident_a_id=source_incident_id,
                incident_b_id=target_incident_id,
                link_type=IncidentLinkType.RELATED_CLUSTER.value,
                confidence=1.0,
                status="approved",
            )
            session.add(inc_link)

        session.flush()

        audit_event = self.audit_repo.record_event(
            session=session,
            action="incident.cluster_linked",
            actor_id=dispatcher_id,
            entity_type="incident",
            entity_id=target_incident_id,
            payload={
                "source_incident_id": str(source_incident_id),
                "target_incident_id": str(target_incident_id),
                "reason": reason,
            },
        )

        return MergeActionResult(
            merge_event_id=None,
            source_incident_id=source_incident_id,
            target_incident_id=target_incident_id,
            status="approved",
            action="related_cluster",
            audit_event_id=audit_event.id,
            reassigned_report_count=0,
        )

    def _unmerge(
        self,
        source_incident_id: uuid.UUID,
        target_incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        reason: str,
        merge_event_id: Optional[uuid.UUID],
        session: Session,
    ) -> MergeActionResult:
        # Find active merge event
        stmt = select(EntityMergeEventModel).where(
            EntityMergeEventModel.source_entity_id == source_incident_id,
            EntityMergeEventModel.target_entity_id == target_incident_id,
            EntityMergeEventModel.status == "active",
        )
        if merge_event_id:
            stmt = stmt.where(EntityMergeEventModel.id == merge_event_id)

        merge_event = session.scalars(stmt).first()
        if not merge_event:
            raise KeyError(
                f"No active merge event found between source {source_incident_id} and target {target_incident_id}"
            )

        now = utc_now()
        merge_event.status = "reversed"
        merge_event.reversed_at = now
        merge_event.reversed_by = dispatcher_id

        # Re-open source incident
        source_inc = session.get(IncidentModel, source_incident_id)
        if source_inc:
            facts = dict(source_inc.severity_facts or {})
            restored = facts.pop("status_before_merge", IncidentStatus.UNVERIFIED.value)
            facts.pop("merged_into", None)
            facts.pop("merge_event_id", None)
            source_inc.severity_facts = facts
            source_inc.status = (
                restored
                if restored
                in (
                    IncidentStatus.UNVERIFIED.value,
                    IncidentStatus.UNDER_REVIEW.value,
                    IncidentStatus.VERIFIED.value,
                )
                else IncidentStatus.UNVERIFIED.value
            )
            source_inc.merged_into_id = None

        # Remove reports attached to target during this merge
        del_stmt = select(IncidentReportModel).where(
            IncidentReportModel.incident_id == target_incident_id,
            IncidentReportModel.linked_by == f"merge:{merge_event.id}",
        )
        removed_count = 0
        for r_link in session.scalars(del_stmt).all():
            session.delete(r_link)
            removed_count += 1

        # Revert link to pending_review
        link_stmt = select(IncidentLinkModel).where(
            ((IncidentLinkModel.incident_a_id == source_incident_id) & (IncidentLinkModel.incident_b_id == target_incident_id))
            | ((IncidentLinkModel.incident_a_id == target_incident_id) & (IncidentLinkModel.incident_b_id == source_incident_id))
        )
        inc_link = session.scalars(link_stmt).first()
        if inc_link:
            inc_link.status = "pending_review"
            inc_link.reviewed_by = dispatcher_id
            inc_link.reviewed_at = utc_now()
            inc_link.review_reason = reason

        session.flush()

        audit_event = self.audit_repo.record_event(
            session=session,
            action="incident.unmerged",
            actor_id=dispatcher_id,
            entity_type="incident",
            entity_id=target_incident_id,
            payload={
                "source_incident_id": str(source_incident_id),
                "target_incident_id": str(target_incident_id),
                "merge_event_id": str(merge_event.id),
                "reason": reason,
                "removed_report_count": removed_count,
            },
        )

        logger.info(
            "Reversed merge %s: restored incident %s from %s",
            merge_event.id,
            source_incident_id,
            target_incident_id,
        )

        return MergeActionResult(
            merge_event_id=merge_event.id,
            source_incident_id=source_incident_id,
            target_incident_id=target_incident_id,
            status="reversed",
            action="unmerged",
            audit_event_id=audit_event.id,
            reassigned_report_count=removed_count,
        )
