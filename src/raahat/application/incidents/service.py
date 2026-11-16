"""Incident read models and commands.

Reads are single SQL statements returning everything a list row or the map
needs, so the interface never fetches per-incident detail to draw a list.
Commands validate against the lifecycle, change state, and append an audit
record in the caller's transaction.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from raahat.application.triage import IncidentTriageService
from raahat.application.triage.service import OVERRIDABLE_FACTS
from raahat.domain.incidents.lifecycle import (
    CLOSURE_REASONS,
    OPERATOR_SETTABLE,
    InvalidTransitionError,
    ensure_transition,
)
from raahat.domain.shared.enums import IncidentCategory, IncidentStatus, PriorityLevel
from raahat.infrastructure.database.models.evidence import EvidenceItemModel
from raahat.infrastructure.database.models.incident import IncidentModel, IncidentReportModel
from raahat.infrastructure.database.models.operation import AssignmentModel
from raahat.infrastructure.database.repositories.audit import (
    PostgresAuditRepository,
    append_audit,
)
from raahat.infrastructure.database.repositories.evidence import PostgresEvidenceRepository

PRIORITY_RANK = {
    PriorityLevel.CRITICAL_REVIEW.value: 0,
    PriorityLevel.URGENT.value: 1,
    # Not yet assessed sorts above routine work: unknown never lowers priority.
    PriorityLevel.UNASSESSED.value: 2,
    PriorityLevel.STANDARD.value: 3,
    PriorityLevel.LOW.value: 4,
}
SORTS = {
    "priority": "priority_rank ASC, i.created_at ASC",
    "newest": "i.created_at DESC",
    "oldest": "i.created_at ASC",
    "updated": "i.updated_at DESC",
    "reference": "i.reference ASC",
}

# Facts an operator can correct, with the value type each accepts.
FACT_TYPES: dict[str, type | tuple[type, ...]] = {
    "people_count": int,
    "trapped_status": bool,
    "medical_emergency": bool,
    "is_life_threatening_medical": bool,
    "vulnerable_present": bool,
    "water_level_trend": str,
    "water_depth_cm": (int, float),
    "water_entering_occupied_floor": bool,
    "current_floor": str,
    "hazards": list,
    "relief_needs": list,
}
assert set(FACT_TYPES) == set(OVERRIDABLE_FACTS)

# Evidence attribute -> fact name, for the provenance sheet.
_ATTRIBUTE_TO_FACT = {
    "people_count": "people_count",
    "trapped_status": "trapped_status",
    "medical_emergency": "medical_emergency",
    "life_threatening_medical": "is_life_threatening_medical",
    "vulnerable_persons": "vulnerable_present",
    "water_level_trend": "water_level_trend",
    "water_depth_cm": "water_depth_cm",
    "water_entering_occupied_floor": "water_entering_occupied_floor",
    "current_floor": "current_floor",
    "hazard": "hazards",
    "relief_need": "relief_needs",
    "category": "category",
    "summary": "summary",
}


class IncidentError(ValueError):
    """A command was rejected for a reason the operator can act on."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


_LIST_SELECT = """
    SELECT i.id, i.reference, i.disaster_id, i.status, i.category, i.summary,
           i.operational_priority, i.severity_facts, i.fact_overrides, i.triage,
           i.source_channel, i.location_description, i.location_status, i.location_source,
           i.location_label, i.location_confidence, i.location_uncertainty_m,
           ST_Y(i.location::geometry) AS latitude, ST_X(i.location::geometry) AS longitude,
           i.created_at, i.updated_at, i.verified_at, i.resolved_at, i.closed_at,
           i.closure_reason, i.merged_into_id,
           CASE i.operational_priority
                WHEN 'critical_review' THEN 0 WHEN 'urgent' THEN 1 WHEN 'unassessed' THEN 2
                WHEN 'standard' THEN 3 ELSE 4 END AS priority_rank,
           (SELECT count(*) FROM incident_reports ir WHERE ir.incident_id = i.id) AS report_count,
           (SELECT count(*) FROM assignments a
             WHERE a.incident_id = i.id AND a.status = 'approved') AS active_assignments,
           (SELECT count(*) FROM incident_links l
             WHERE (l.incident_a_id = i.id OR l.incident_b_id = i.id)
               AND l.status = 'pending_review') AS pending_duplicates
    FROM incidents i
"""


@dataclass(frozen=True)
class IncidentQuery:
    disaster_id: Optional[uuid.UUID] = None
    statuses: Sequence[str] = ()
    priorities: Sequence[str] = ()
    categories: Sequence[str] = ()
    search: Optional[str] = None
    location_status: Optional[str] = None
    needs_review: Optional[bool] = None
    bbox: Optional[tuple[float, float, float, float]] = None  # west, south, east, north
    sort: str = "priority"
    limit: int = 50
    offset: int = 0


def _where(query: IncidentQuery) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if query.disaster_id is not None:
        clauses.append("i.disaster_id = :disaster_id")
        params["disaster_id"] = query.disaster_id
    for name, values, column in (
        ("status", query.statuses, "i.status"),
        ("priority", query.priorities, "i.operational_priority"),
        ("category", query.categories, "i.category"),
    ):
        if values:
            keys = []
            for index, value in enumerate(values):
                key = f"{name}_{index}"
                params[key] = value
                keys.append(f":{key}")
            clauses.append(f"{column} IN ({', '.join(keys)})")
    if query.search:
        clauses.append(
            "(i.reference ILIKE :search OR i.summary ILIKE :search "
            "OR i.location_description ILIKE :search OR i.location_label ILIKE :search "
            "OR EXISTS (SELECT 1 FROM incident_reports ir JOIN reports r ON r.id = ir.report_id "
            "WHERE ir.incident_id = i.id AND (r.original_text ILIKE :search "
            "OR r.translated_text ILIKE :search)))"
        )
        params["search"] = f"%{query.search.strip()}%"
    if query.location_status:
        clauses.append("i.location_status = :location_status")
        params["location_status"] = query.location_status
    if query.needs_review is True:
        clauses.append(
            "(i.status IN ('unverified','under_review') OR EXISTS ("
            "SELECT 1 FROM incident_links l WHERE (l.incident_a_id = i.id OR l.incident_b_id = i.id)"
            " AND l.status = 'pending_review'))"
        )
    if query.bbox is not None:
        clauses.append(
            "i.location IS NOT NULL AND ST_Intersects(i.location::geometry, "
            "ST_MakeEnvelope(:west, :south, :east, :north, 4326))"
        )
        params.update(zip(("west", "south", "east", "north"), query.bbox))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_incidents(session: Session, query: IncidentQuery) -> tuple[list[dict[str, Any]], int]:
    where, params = _where(query)
    total = session.execute(text(f"SELECT count(*) FROM incidents i{where}"), params).scalar_one()
    order = SORTS.get(query.sort, SORTS["priority"])
    rows = session.execute(
        text(f"{_LIST_SELECT}{where} ORDER BY {order}, i.id LIMIT :limit OFFSET :offset"),
        {**params, "limit": query.limit, "offset": query.offset},
    ).mappings().all()
    return [dict(r) for r in rows], total


def get_incident_row(session: Session, incident_id: uuid.UUID) -> Optional[dict[str, Any]]:
    row = session.execute(
        text(f"{_LIST_SELECT} WHERE i.id = :id"), {"id": incident_id}
    ).mappings().first()
    return dict(row) if row else None


def resolve_incident_id(session: Session, identifier: str) -> Optional[uuid.UUID]:
    """Accept either the UUID or the human reference (INC-000042)."""
    try:
        return uuid.UUID(identifier)
    except ValueError:
        return session.execute(
            select(IncidentModel.id).where(IncidentModel.reference == identifier.upper())
        ).scalar_one_or_none()


def status_counts(session: Session, disaster_id: Optional[uuid.UUID]) -> dict[str, Any]:
    """Counts by status and priority for open incidents. Computed, not cached."""
    params: dict[str, Any] = {}
    scope = ""
    if disaster_id is not None:
        scope = " AND disaster_id = :disaster_id"
        params["disaster_id"] = disaster_id
    by_status = session.execute(
        text(f"SELECT status, count(*) FROM incidents WHERE TRUE{scope} GROUP BY status"), params
    ).all()
    by_priority = session.execute(
        text(
            "SELECT operational_priority, count(*) FROM incidents WHERE status IN "
            f"('unverified','under_review','verified','assigned','in_progress'){scope} "
            "GROUP BY operational_priority"
        ),
        params,
    ).all()
    without_location = session.execute(
        text(
            "SELECT count(*) FROM incidents WHERE location_status = 'none' AND status IN "
            f"('unverified','under_review','verified','assigned','in_progress'){scope}"
        ),
        params,
    ).scalar_one()
    return {
        "by_status": {s: c for s, c in by_status},
        "open_by_priority": {p: c for p, c in by_priority},
        "open_without_location": without_location,
        "generated_at": _now(),
    }


# --------------------------------------------------------------------- facts
def fact_sheet(session: Session, incident: IncidentModel) -> list[dict[str, Any]]:
    """Each fact with its current value and where that value came from.

    ``origin`` is ``operator`` when a person set it, otherwise ``extracted``;
    ``sources`` lists the evidence behind an extracted value (extractor, model,
    supporting quote, report). A fact with no value and no evidence is unknown.
    """
    report_ids = [
        r
        for (r,) in session.execute(
            select(IncidentReportModel.report_id).where(IncidentReportModel.incident_id == incident.id)
        ).all()
    ]
    evidence_by_fact: dict[str, list[dict[str, Any]]] = {}
    if report_ids:
        items = session.execute(
            select(EvidenceItemModel).where(EvidenceItemModel.report_id.in_(report_ids))
        ).scalars().all()
        for item in items:
            fact = _ATTRIBUTE_TO_FACT.get(item.attribute)
            if fact is None:
                continue
            span = item.spans[0] if item.spans else None
            reference = (span.source_reference if span else None) or {}
            evidence_by_fact.setdefault(fact, []).append(
                {
                    "report_id": item.report_id,
                    "value": item.value,
                    "extractor": reference.get("extractor", "unknown"),
                    "model": reference.get("model"),
                    "quote": span.source_text if span else None,
                    "note": reference.get("note"),
                    "confidence": item.confidence,
                }
            )

    facts = dict(incident.severity_facts or {})
    overrides = dict(incident.fact_overrides or {})
    sheet: list[dict[str, Any]] = []
    for name in (*FACT_TYPES, "category", "summary"):
        if name == "category":
            value: Any = None if incident.category == IncidentCategory.UNKNOWN.value else incident.category
        elif name == "summary":
            value = incident.summary
        else:
            value = facts.get(name)
            if isinstance(value, (list, tuple)) and not value:
                value = None
        override = overrides.get(name) if isinstance(overrides.get(name), dict) else None
        sheet.append(
            {
                "name": name,
                "value": value,
                "known": value is not None,
                "origin": "operator" if override else ("extracted" if value is not None else "unknown"),
                "set_by": override.get("by") if override else None,
                "set_at": override.get("at") if override else None,
                "sources": evidence_by_fact.get(name, []),
            }
        )
    return sheet


# ------------------------------------------------------------------ commands
class IncidentCommands:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._triage = IncidentTriageService(
            evidence_repo=PostgresEvidenceRepository(session_factory),
            audit_repo=PostgresAuditRepository(session_factory),
            session_factory=session_factory,
        )

    def change_status(
        self,
        session: Session,
        *,
        incident_id: uuid.UUID,
        target: IncidentStatus,
        actor_id: uuid.UUID,
        note: Optional[str] = None,
        closure_reason: Optional[str] = None,
    ) -> IncidentModel:
        incident = session.get(IncidentModel, incident_id, with_for_update=True)
        if incident is None:
            raise LookupError("Incident not found")
        current = IncidentStatus(incident.status)
        if target not in OPERATOR_SETTABLE:
            raise IncidentError(
                f"Status '{target.value}' is set by the system from assignment or merge activity"
            )
        if current == IncidentStatus.DUPLICATE:
            raise IncidentError("A duplicate is restored by reversing its merge")
        ensure_transition(current, target)

        active = session.execute(
            select(AssignmentModel.id).where(
                AssignmentModel.incident_id == incident_id, AssignmentModel.status == "approved"
            )
        ).first()
        if active and target in (IncidentStatus.CLOSED, IncidentStatus.UNDER_REVIEW, IncidentStatus.VERIFIED):
            raise IncidentError(
                "Resources are still committed to this incident. Complete or cancel their "
                "assignments first."
            )
        if target == IncidentStatus.CLOSED:
            if closure_reason not in CLOSURE_REASONS:
                raise IncidentError(
                    "Closing requires a reason: " + ", ".join(CLOSURE_REASONS)
                )
            if closure_reason in ("false_report", "other") and not (note and note.strip()):
                raise IncidentError("A note is required for this closure reason")

        now = _now()
        incident.status = target.value
        incident.updated_at = now
        if target == IncidentStatus.VERIFIED and current in (
            IncidentStatus.UNVERIFIED, IncidentStatus.UNDER_REVIEW,
        ):
            incident.verified_by = actor_id
            incident.verified_at = now
            incident.last_confirmed_at = now
        if target == IncidentStatus.RESOLVED:
            incident.resolved_at = now
        if target == IncidentStatus.CLOSED:
            incident.closed_at = now
            incident.closure_reason = closure_reason
        if target == IncidentStatus.UNDER_REVIEW and current == IncidentStatus.CLOSED:
            incident.closed_at = None
            incident.closure_reason = None
        session.flush()
        append_audit(
            session,
            action="incident.status_changed",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident.id,
            disaster_id=incident.disaster_id,
            payload={
                "from": current.value,
                "to": target.value,
                "note": note,
                "closure_reason": closure_reason,
            },
        )
        return incident

    def correct(
        self,
        session: Session,
        *,
        incident_id: uuid.UUID,
        actor_id: uuid.UUID,
        facts: Optional[dict[str, Any]] = None,
        category: Optional[IncidentCategory] = None,
        summary: Optional[str] = None,
        location_description: Optional[str] = None,
        priority: Optional[PriorityLevel] = None,
        clear_priority_override: bool = False,
        note: Optional[str] = None,
    ) -> IncidentModel:
        """Apply operator corrections. Extracted evidence is left untouched; the
        correction is stored beside it and takes precedence."""
        incident = session.get(IncidentModel, incident_id, with_for_update=True)
        if incident is None:
            raise LookupError("Incident not found")
        if incident.status in (IncidentStatus.CLOSED.value, IncidentStatus.DUPLICATE.value):
            raise IncidentError("A closed or merged incident cannot be edited. Reopen it first.")

        overrides = dict(incident.fact_overrides or {})
        current_facts = dict(incident.severity_facts or {})
        stamp = {"by": str(actor_id), "at": _now().isoformat()}
        changes: dict[str, dict[str, Any]] = {}

        for name, value in (facts or {}).items():
            if name not in FACT_TYPES:
                raise IncidentError(f"'{name}' is not a correctable fact")
            expected = FACT_TYPES[name]
            if value is not None:
                if isinstance(value, bool) and expected is not bool:
                    raise IncidentError(f"'{name}' has the wrong type")
                if not isinstance(value, expected):
                    raise IncidentError(f"'{name}' has the wrong type")
                if name == "people_count" and not 0 <= value <= 100_000:
                    raise IncidentError("People count is out of range")
                if name == "water_depth_cm" and not 0 <= value <= 3000:
                    raise IncidentError("Water depth is out of range")
                if name == "water_level_trend" and value not in ("rising", "falling", "stable", "receded"):
                    raise IncidentError("Water level trend must be rising, falling, stable or receded")
                if expected is list and not all(isinstance(v, str) and v.strip() for v in value):
                    raise IncidentError(f"'{name}' must be a list of text values")
            previous = current_facts.get(name)
            if isinstance(previous, list) and not previous:
                previous = None
            if previous == value and name not in overrides:
                continue
            overrides[name] = {"value": value, **stamp}
            changes[name] = {"from": previous, "to": value}

        if category is not None and category.value != incident.category:
            changes["category"] = {"from": incident.category, "to": category.value}
            incident.category = category.value
            overrides["category"] = {"value": category.value, **stamp}
        if summary is not None and summary.strip() != (incident.summary or ""):
            changes["summary"] = {"from": incident.summary, "to": summary.strip() or None}
            incident.summary = summary.strip() or None
            overrides["summary"] = {"value": incident.summary, **stamp}
        if location_description is not None and location_description.strip() != (
            incident.location_description or ""
        ):
            changes["location_description"] = {
                "from": incident.location_description,
                "to": location_description.strip() or None,
            }
            incident.location_description = location_description.strip() or None

        if priority is not None:
            if not (note and note.strip()):
                raise IncidentError("Changing priority by hand requires a note explaining why")
            changes["operational_priority"] = {
                "from": incident.operational_priority, "to": priority.value,
            }
            overrides["operational_priority"] = {"value": priority.value, "reason": note, **stamp}
        elif clear_priority_override and "operational_priority" in overrides:
            changes["operational_priority"] = {
                "from": incident.operational_priority, "to": "policy",
            }
            del overrides["operational_priority"]

        if not changes:
            return incident
        incident.fact_overrides = overrides
        incident.updated_at = _now()
        session.flush()
        append_audit(
            session,
            action="incident.corrected",
            actor_id=actor_id,
            entity_type="incident",
            entity_id=incident.id,
            disaster_id=incident.disaster_id,
            payload={"changes": changes, "note": note},
        )
        # Corrections feed the same triage rules as extracted evidence.
        self._triage._triage_with_session(incident.id, session, actor_id=actor_id)
        session.refresh(incident)
        return incident


__all__ = [
    "FACT_TYPES",
    "PRIORITY_RANK",
    "IncidentCommands",
    "IncidentError",
    "IncidentQuery",
    "InvalidTransitionError",
    "fact_sheet",
    "get_incident_row",
    "list_incidents",
    "resolve_incident_id",
    "status_counts",
]
