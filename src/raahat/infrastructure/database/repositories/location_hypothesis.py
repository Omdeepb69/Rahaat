"""Location hypothesis repository implementations."""
from __future__ import annotations

import binascii
import struct
import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from sqlalchemy.orm import Session, sessionmaker

from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import VerificationStatus
from raahat.infrastructure.database.models.location import LocationHypothesisModel


def parse_wkb_point(raw_data: Any) -> PointCoordinates:
    """Parse WGS84 point from EWKB bytes or WKT string without Shapely dependency."""
    if isinstance(raw_data, str):
        if "POINT" in raw_data.upper():
            return PointCoordinates.from_wkt(raw_data)
        raw = binascii.unhexlify(raw_data.strip())
    elif hasattr(raw_data, "data"):
        if isinstance(raw_data.data, str):
            if "POINT" in raw_data.data.upper():
                return PointCoordinates.from_wkt(raw_data.data)
            raw = binascii.unhexlify(raw_data.data.strip())
        else:
            raw = bytes(raw_data.data)
    elif isinstance(raw_data, (bytes, memoryview)):
        raw = bytes(raw_data)
    else:
        raise ValueError(f"Unsupported location data type: {type(raw_data)}")

    endian = "<" if raw[0] == 1 else ">"
    geom_type = struct.unpack(endian + "I", raw[1:5])[0]
    has_srid = bool(geom_type & 0x20000000)
    offset = 9 if has_srid else 5
    lon, lat = struct.unpack(endian + "dd", raw[offset : offset + 16])
    return PointCoordinates(latitude=lat, longitude=lon)


def _model_to_hypothesis(model: LocationHypothesisModel) -> LocationHypothesis:
    """Convert a database model to domain value object."""
    coords = parse_wkb_point(model.location)

    return LocationHypothesis(
        id=model.id,
        incident_id=model.incident_id,
        coordinates=coords,
        candidate_label=model.candidate_label,
        source_evidence_id=model.source_evidence_id,
        probability=model.probability,
        uncertainty_radius_m=model.uncertainty_radius_m,
        verification_status=VerificationStatus(model.verification_status),
        created_at=model.created_at,
    )


@runtime_checkable
class LocationHypothesisRepository(Protocol):
    """Protocol for persisting and retrieving location hypotheses."""

    def get_by_id(self, hypothesis_id: uuid.UUID) -> Optional[LocationHypothesis]: ...

    def list_by_incident(self, incident_id: uuid.UUID) -> list[LocationHypothesis]: ...

    def create(self, hypothesis: LocationHypothesis) -> LocationHypothesis: ...

    def update_status(
        self,
        hypothesis_id: uuid.UUID,
        status: VerificationStatus,
        uncertainty_radius_m: Optional[float] = None,
    ) -> Optional[LocationHypothesis]: ...


class PostgresLocationHypothesisRepository:
    """PostgreSQL implementation of LocationHypothesisRepository."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_by_id(self, hypothesis_id: uuid.UUID) -> Optional[LocationHypothesis]:
        with self._session_factory() as session:
            model = session.get(LocationHypothesisModel, hypothesis_id)
            return _model_to_hypothesis(model) if model else None

    def list_by_incident(self, incident_id: uuid.UUID) -> list[LocationHypothesis]:
        with self._session_factory() as session:
            models = (
                session.query(LocationHypothesisModel)
                .filter_by(incident_id=incident_id)
                .order_by(LocationHypothesisModel.created_at.asc())
                .all()
            )
            return [_model_to_hypothesis(m) for m in models]

    def create(self, hypothesis: LocationHypothesis) -> LocationHypothesis:
        wkt = f"SRID=4326;POINT({hypothesis.coordinates.longitude:.7f} {hypothesis.coordinates.latitude:.7f})"
        model = LocationHypothesisModel(
            id=hypothesis.id,
            incident_id=hypothesis.incident_id,
            location=wkt,
            candidate_label=hypothesis.candidate_label,
            source_evidence_id=hypothesis.source_evidence_id,
            probability=hypothesis.probability,
            uncertainty_radius_m=hypothesis.uncertainty_radius_m,
            verification_status=hypothesis.verification_status.value,
            created_at=hypothesis.created_at,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return _model_to_hypothesis(model)

    def update_status(
        self,
        hypothesis_id: uuid.UUID,
        status: VerificationStatus,
        uncertainty_radius_m: Optional[float] = None,
    ) -> Optional[LocationHypothesis]:
        with self._session_factory() as session:
            model = session.get(LocationHypothesisModel, hypothesis_id)
            if not model:
                return None
            model.verification_status = status.value
            if uncertainty_radius_m is not None:
                model.uncertainty_radius_m = uncertainty_radius_m
            session.commit()
            session.refresh(model)
            return _model_to_hypothesis(model)


class InMemoryLocationHypothesisRepository:
    """In-memory implementation of LocationHypothesisRepository for testing."""

    def __init__(self, hypotheses: Optional[list[LocationHypothesis]] = None) -> None:
        self._hypotheses: dict[uuid.UUID, LocationHypothesis] = {
            h.id: h for h in (hypotheses or [])
        }

    def get_by_id(self, hypothesis_id: uuid.UUID) -> Optional[LocationHypothesis]:
        return self._hypotheses.get(hypothesis_id)

    def list_by_incident(self, incident_id: uuid.UUID) -> list[LocationHypothesis]:
        matching = [
            h for h in self._hypotheses.values() if h.incident_id == incident_id
        ]
        return sorted(matching, key=lambda h: h.created_at)

    def create(self, hypothesis: LocationHypothesis) -> LocationHypothesis:
        self._hypotheses[hypothesis.id] = hypothesis
        return hypothesis

    def update_status(
        self,
        hypothesis_id: uuid.UUID,
        status: VerificationStatus,
        uncertainty_radius_m: Optional[float] = None,
    ) -> Optional[LocationHypothesis]:
        existing = self._hypotheses.get(hypothesis_id)
        if not existing:
            return None
        updated = LocationHypothesis(
            id=existing.id,
            incident_id=existing.incident_id,
            coordinates=existing.coordinates,
            candidate_label=existing.candidate_label,
            source_evidence_id=existing.source_evidence_id,
            probability=existing.probability,
            uncertainty_radius_m=(
                uncertainty_radius_m
                if uncertainty_radius_m is not None
                else existing.uncertainty_radius_m
            ),
            verification_status=status,
            created_at=existing.created_at,
        )
        self._hypotheses[hypothesis_id] = updated
        return updated
