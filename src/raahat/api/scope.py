"""Jurisdiction enforcement for authenticated routes.

``current_user`` records the caller's jurisdiction on the request's database
session. Every route that reads or changes operational data checks the
operation it touches here. Anything outside the caller's jurisdiction is
reported as not found, so its existence is not revealed.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from raahat.security.jurisdiction import Jurisdiction

_KEY = "jurisdiction"


def bind(session: Session, jurisdiction: Jurisdiction) -> None:
    session.info[_KEY] = jurisdiction


def of(session: Session) -> Jurisdiction:
    found = session.info.get(_KEY)
    if not isinstance(found, Jurisdiction):
        raise RuntimeError("No jurisdiction bound to this session")
    return found


def _check(session: Session, sql: str, ident: uuid.UUID, what: str) -> None:
    row = session.execute(text(sql), {"id": ident}).first()
    if row is None or not of(session).covers(row.state_code, row.district_code):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def ensure_operation(session: Session, disaster_id: uuid.UUID) -> uuid.UUID:
    _check(session, "SELECT state_code, district_code FROM disasters WHERE id = :id", disaster_id, "Operation")
    return disaster_id


def ensure_incident(session: Session, incident_id: uuid.UUID) -> uuid.UUID:
    _check(
        session,
        "SELECT d.state_code, d.district_code FROM incidents x JOIN disasters d ON d.id = x.disaster_id "
        "WHERE x.id = :id",
        incident_id,
        "Incident",
    )
    return incident_id


def ensure_report(session: Session, report_id: uuid.UUID) -> uuid.UUID:
    _check(
        session,
        "SELECT d.state_code, d.district_code FROM reports x JOIN disasters d ON d.id = x.disaster_id "
        "WHERE x.id = :id",
        report_id,
        "Report",
    )
    return report_id


def ensure_resource(session: Session, resource_id: uuid.UUID) -> uuid.UUID:
    _check(
        session,
        "SELECT d.state_code, d.district_code FROM resources x JOIN disasters d ON d.id = x.disaster_id "
        "WHERE x.id = :id",
        resource_id,
        "Resource",
    )
    return resource_id


def ensure_assignment(session: Session, assignment_id: uuid.UUID) -> uuid.UUID:
    _check(
        session,
        "SELECT d.state_code, d.district_code FROM assignments a JOIN incidents i ON i.id = a.incident_id "
        "JOIN disasters d ON d.id = i.disaster_id WHERE a.id = :id",
        assignment_id,
        "Assignment",
    )
    return assignment_id


def list_filter(
    session: Session, disaster_id: Optional[uuid.UUID], incident_id: Optional[uuid.UUID] = None
) -> Optional[uuid.UUID]:
    """Validate the filters of a list request.

    A national account may list across operations. Any other account must name
    an operation (or an incident) inside its jurisdiction.
    """
    if disaster_id is not None:
        ensure_operation(session, disaster_id)
    if incident_id is not None:
        ensure_incident(session, incident_id)
    if disaster_id is None and incident_id is None and not of(session).is_national:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose an operation")
    return disaster_id


def visible_operations(jurisdiction: Jurisdiction):
    """A SELECT of operation ids inside ``jurisdiction``, or None for national accounts."""
    from sqlalchemy import select

    from raahat.infrastructure.database.models.disaster import DisasterModel

    if jurisdiction.is_national:
        return None
    stmt = select(DisasterModel.id).where(DisasterModel.state_code == jurisdiction.state_code)
    if jurisdiction.district_code is not None:
        stmt = stmt.where(DisasterModel.district_code == jurisdiction.district_code)
    return stmt
