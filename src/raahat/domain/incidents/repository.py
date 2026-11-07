"""IncidentRepository protocol and pure-Python in-memory implementation."""
from __future__ import annotations

import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from raahat.domain.incidents.incident import Incident, IncidentLink, IncidentReportLink
from raahat.domain.shared.enums import IncidentStatus


@runtime_checkable
class IncidentRepository(Protocol):
    """Protocol for persisting and retrieving incidents, report links, and incident links."""

    def save(
        self,
        incident: Incident,
        session: Optional[Any] = None,
    ) -> Incident:
        """Persist or update an incident."""
        ...

    def get_by_id(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[Incident]:
        """Retrieve an incident by primary key."""
        ...

    def list_active_by_disaster(
        self,
        disaster_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[Incident]:
        """List active (unresolved, unclosed) incidents for a disaster."""
        ...

    def save_report_link(
        self,
        link: IncidentReportLink,
        session: Optional[Any] = None,
    ) -> IncidentReportLink:
        """Link a report to an incident."""
        ...

    def list_reports_for_incident(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[uuid.UUID]:
        """List all report IDs linked to an incident."""
        ...

    def save_incident_link(
        self,
        link: IncidentLink,
        session: Optional[Any] = None,
    ) -> IncidentLink:
        """Record a potential duplicate or conflicting link between two incidents."""
        ...

    def list_links_for_incident(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[IncidentLink]:
        """List all incident links involving this incident."""
        ...


class InMemoryIncidentRepository:
    """Pure-Python in-memory implementation of IncidentRepository for deterministic unit tests."""

    def __init__(self) -> None:
        self._incidents: dict[uuid.UUID, Incident] = {}
        self._report_links: list[IncidentReportLink] = []
        self._incident_links: list[IncidentLink] = []

    def save(
        self,
        incident: Incident,
        session: Optional[Any] = None,
    ) -> Incident:
        self._incidents[incident.id] = incident
        return incident

    def get_by_id(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> Optional[Incident]:
        return self._incidents.get(incident_id)

    def list_active_by_disaster(
        self,
        disaster_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[Incident]:
        return [
            inc
            for inc in self._incidents.values()
            if inc.disaster_id == disaster_id
            and inc.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
        ]

    def save_report_link(
        self,
        link: IncidentReportLink,
        session: Optional[Any] = None,
    ) -> IncidentReportLink:
        # Avoid duplicate report links
        for idx, existing in enumerate(self._report_links):
            if existing.incident_id == link.incident_id and existing.report_id == link.report_id:
                self._report_links[idx] = link
                return link
        self._report_links.append(link)
        return link

    def list_reports_for_incident(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[uuid.UUID]:
        return [
            link.report_id
            for link in self._report_links
            if link.incident_id == incident_id
        ]

    def save_incident_link(
        self,
        link: IncidentLink,
        session: Optional[Any] = None,
    ) -> IncidentLink:
        for idx, existing in enumerate(self._incident_links):
            if existing.id == link.id:
                self._incident_links[idx] = link
                return link
        self._incident_links.append(link)
        return link

    def list_links_for_incident(
        self,
        incident_id: uuid.UUID,
        session: Optional[Any] = None,
    ) -> list[IncidentLink]:
        return [
            link
            for link in self._incident_links
            if link.incident_a_id == incident_id or link.incident_b_id == incident_id
        ]

