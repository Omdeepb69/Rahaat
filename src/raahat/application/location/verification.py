"""Location verification application service and dispatcher confirmation workflows."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import IncidentStatus, VerificationStatus
from raahat.infrastructure.database.base import utc_now
from raahat.infrastructure.database.models.incident import IncidentModel
from raahat.infrastructure.database.repositories.audit import (
    AuditRepository,
    PostgresAuditRepository,
)
from raahat.infrastructure.database.repositories.location_hypothesis import (
    LocationHypothesisRepository,
    PostgresLocationHypothesisRepository,
)


class LocationVerificationResult(BaseModel):
    """Result of dispatcher verifying an incident's geographic location."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    incident_id: uuid.UUID
    verified_hypothesis: LocationHypothesis
    audit_event_id: uuid.UUID
    all_hypotheses: list[LocationHypothesis]


class LocationVerificationService:
    """Service orchestrating dispatcher location verification and audit logging."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        hypothesis_repo: Optional[LocationHypothesisRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ) -> None:
        self._session_factory = session_factory
        self._hypothesis_repo = (
            hypothesis_repo or PostgresLocationHypothesisRepository(session_factory)
        )
        self._audit_repo = audit_repo or PostgresAuditRepository(session_factory)

    def get_hypotheses_history(
        self,
        incident_id: uuid.UUID,
    ) -> list[LocationHypothesis]:
        """Retrieve full historical chain of candidate hypotheses for an incident."""
        # Ensure incident exists
        with self._session_factory() as session:
            incident = session.get(IncidentModel, incident_id)
            if not incident:
                raise KeyError(f"Incident {incident_id} not found")

        return self._hypothesis_repo.list_by_incident(incident_id)

    def verify_location(
        self,
        incident_id: uuid.UUID,
        dispatcher_id: uuid.UUID,
        hypothesis_id: Optional[uuid.UUID] = None,
        coordinates: Optional[PointCoordinates] = None,
        candidate_label: Optional[str] = None,
        uncertainty_radius_m: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> LocationVerificationResult:
        """Confirm an incident location hypothesis, update incident, and log audit event.

        Preserves all prior hypotheses in the database without deletion.
        """
        if hypothesis_id is None and coordinates is None:
            raise ValueError("Either hypothesis_id or coordinates must be provided")

        with self._session_factory() as session:
            incident = session.get(IncidentModel, incident_id)
            if not incident:
                raise KeyError(f"Incident {incident_id} not found")

            # 1. Update existing hypothesis or create new verified hypothesis
            verified_hyp: Optional[LocationHypothesis] = None
            if hypothesis_id is not None:
                hyp = self._hypothesis_repo.get_by_id(hypothesis_id)
                if not hyp or hyp.incident_id != incident_id:
                    raise KeyError(
                        f"Location hypothesis {hypothesis_id} not found for incident {incident_id}"
                    )
                verified_hyp = self._hypothesis_repo.update_status(
                    hypothesis_id=hypothesis_id,
                    status=VerificationStatus.CONFIRMED,
                    uncertainty_radius_m=uncertainty_radius_m,
                )
            else:
                assert coordinates is not None
                new_hyp = LocationHypothesis(
                    incident_id=incident_id,
                    coordinates=coordinates,
                    candidate_label=candidate_label or "Dispatcher confirmed location",
                    probability=1.0,
                    uncertainty_radius_m=(
                        uncertainty_radius_m if uncertainty_radius_m is not None else 10.0
                    ),
                    verification_status=VerificationStatus.CONFIRMED,
                )
                verified_hyp = self._hypothesis_repo.create(new_hyp)

            assert verified_hyp is not None

            # 2. Update incident last_confirmed_at and verification status
            incident.last_confirmed_at = utc_now()
            if incident.status == IncidentStatus.UNVERIFIED.value:
                incident.status = IncidentStatus.VERIFIED.value
            session.commit()

        # 3. Create tamper-evident audit record
        audit = self._audit_repo.record_event(
            action="incident.location_verified",
            actor_id=dispatcher_id,
            entity_type="incident",
            entity_id=incident_id,
            payload={
                "hypothesis_id": str(verified_hyp.id),
                "coordinates": {
                    "latitude": verified_hyp.coordinates.latitude,
                    "longitude": verified_hyp.coordinates.longitude,
                },
                "candidate_label": verified_hyp.candidate_label,
                "uncertainty_radius_m": verified_hyp.uncertainty_radius_m,
                "notes": notes,
            },
        )

        all_hypotheses = self._hypothesis_repo.list_by_incident(incident_id)

        return LocationVerificationResult(
            incident_id=incident_id,
            verified_hypothesis=verified_hyp,
            audit_event_id=audit.id,
            all_hypotheses=all_hypotheses,
        )
