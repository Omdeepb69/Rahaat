"""Conservative incident matcher evaluating candidate incidents for incoming reports."""
from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from raahat.domain.evidence.detector import RuleBasedContradictionDetector
from raahat.domain.evidence.evidence import EvidenceItem
from raahat.domain.evidence.extractor import StructuredEvidenceExtractor
from raahat.domain.geospatial.location_hypothesis import LocationHypothesis
from raahat.domain.reports.report import Report
from raahat.domain.shared.coordinates import PointCoordinates
from raahat.domain.shared.enums import (
    IncidentLinkType,
    IncidentStatus,
    PriorityLevel,
    ProcessingStatus,
    SourceType,
    VerificationStatus,
)

from .models import IncidentCandidate, IncidentSnapshot, MatchSignal

# A report is compared only with open incidents that share its phone number,
# lie within CANDIDATE_RADIUS_M of its position, or were opened in the last
# RECENT_WINDOW_HOURS (most recent RECENT_LIMIT). MAX_CANDIDATE_INCIDENTS caps
# the total, which bounds time and memory per report.
CANDIDATE_RADIUS_M = 2000.0
RECENT_WINDOW_HOURS = 12
RECENT_LIMIT = 50
MAX_CANDIDATE_INCIDENTS = 150


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Normalize phone number to last 10 digits for conservative comparison."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) >= 10:
        return digits[-10:]
    return digits if len(digits) >= 7 else None


def extract_phone(report: Report) -> Optional[str]:
    """Extract and normalize contact phone number from report fields and payload."""
    # Check source_identity and channel_reference first
    phone = normalize_phone(report.source_identity)
    if phone:
        return phone

    phone = normalize_phone(report.channel_reference)
    if phone:
        return phone

    # Check raw_payload keys
    payload = report.raw_payload or {}
    candidates = [
        payload.get("phone"),
        payload.get("caller_number"),
        payload.get("contact"),
        payload.get("mobile"),
        payload.get("phone_number"),
    ]

    # Check nested parsed / extracted dicts
    for subkey in ("parsed", "extracted"):
        sub = payload.get(subkey)
        if isinstance(sub, dict):
            candidates.extend([
                sub.get("phone"),
                sub.get("caller_number"),
                sub.get("contact"),
            ])

    for cand in candidates:
        norm = normalize_phone(cand)
        if norm:
            return norm

    return None


def extract_coordinates(report: Report) -> Optional[PointCoordinates]:
    """Extract PointCoordinates from raw payload dictionary."""
    payload = report.raw_payload or {}

    def _try_coords(lat_raw: Any, lon_raw: Any) -> Optional[PointCoordinates]:
        try:
            if lat_raw is not None and lon_raw is not None:
                lat = float(lat_raw)
                lon = float(lon_raw)
                if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                    return PointCoordinates(latitude=lat, longitude=lon)
        except (ValueError, TypeError):
            pass
        return None

    # Direct lat/lon
    c = _try_coords(payload.get("latitude"), payload.get("longitude"))
    if c:
        return c
    c = _try_coords(payload.get("lat"), payload.get("lon") or payload.get("lng"))
    if c:
        return c

    # Nested in coords / location / pin / gps
    for key in ("coords", "coordinates", "location", "pin", "gps"):
        sub = payload.get(key)
        if isinstance(sub, dict):
            c = _try_coords(sub.get("latitude") or sub.get("lat"), sub.get("longitude") or sub.get("lon") or sub.get("lng"))
            if c:
                return c
        elif isinstance(sub, (list, tuple)) and len(sub) == 2:
            # Check if format is [lat, lon] or [lon, lat]
            # Standard GeoJSON is [lon, lat]
            try:
                val0, val1 = float(sub[0]), float(sub[1])
                # If val0 in [-90, 90] and val1 in [-180, 180] -> could be [lat, lon]
                # Default assume [lon, lat] if val0 in [-180, 180] and val1 in [-90, 90]
                if -90.0 <= val1 <= 90.0 and -180.0 <= val0 <= 180.0:
                    return PointCoordinates(latitude=val1, longitude=val0)
                elif -90.0 <= val0 <= 90.0 and -180.0 <= val1 <= 180.0:
                    return PointCoordinates(latitude=val0, longitude=val1)
            except (ValueError, TypeError):
                pass

    # Check nested parsed / extracted
    for subkey in ("parsed", "extracted"):
        sub = payload.get(subkey)
        if isinstance(sub, dict):
            c = _try_coords(sub.get("latitude") or sub.get("lat"), sub.get("longitude") or sub.get("lon") or sub.get("lng"))
            if c:
                return c

    return None


def extract_reported_position(report: Report) -> Optional[PointCoordinates]:
    """Any position recorded with the report, for comparing reports.

    Includes a position the caller's device supplied and one an operator
    entered at intake (``operator_pin``). Only the former is ever labelled as
    the caller's position; this function is for proximity matching only.
    """
    coords = extract_coordinates(report)
    if coords is not None:
        return coords
    pin = (report.raw_payload or {}).get("operator_pin")
    if isinstance(pin, dict):
        try:
            return PointCoordinates(latitude=float(pin["latitude"]), longitude=float(pin["longitude"]))
        except (KeyError, TypeError, ValueError):
            return None
    return None


def extract_name(report: Report) -> Optional[str]:
    """Extract caller or household member name from raw payload."""
    payload = report.raw_payload or {}
    candidates = [
        payload.get("name"),
        payload.get("caller_name"),
        payload.get("family_name"),
        payload.get("household"),
    ]
    for subkey in ("parsed", "extracted"):
        sub = payload.get(subkey)
        if isinstance(sub, dict):
            candidates.extend([
                sub.get("name"),
                sub.get("caller_name"),
                sub.get("family_name"),
            ])

    for cand in candidates:
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    return None


class ConservativeIncidentMatcher:
    """Evaluates candidate incidents against an incoming report conservatively."""

    def __init__(
        self,
        snapshot_provider: Optional[Callable[[uuid.UUID], Sequence[IncidentSnapshot]]] = None,
        extractor: Optional[StructuredEvidenceExtractor] = None,
        detector: Optional[RuleBasedContradictionDetector] = None,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._extractor = extractor or StructuredEvidenceExtractor()
        self._detector = detector or RuleBasedContradictionDetector()

    def find_candidates(
        self,
        report: Report,
        evidence_items: Optional[list[EvidenceItem]] = None,
        session: Optional[Session] = None,
    ) -> list[IncidentCandidate]:
        """Find and rank candidate incidents matching the report."""
        if evidence_items is None:
            evidence_items = self._extractor.extract(report)

        # Retrieve snapshots
        snapshots: list[IncidentSnapshot] = []
        if self._snapshot_provider:
            snapshots = list(self._snapshot_provider(report.disaster_id))
        elif session is not None:
            snapshots = self._load_snapshots_from_db(report, session)

        candidates: list[IncidentCandidate] = []
        report_phone = extract_phone(report)
        report_coords = extract_reported_position(report)
        report_name = extract_name(report)
        report_item_ids = {item.id for item in evidence_items}

        for snap in snapshots:
            if snap.incident.disaster_id != report.disaster_id:
                continue
            if snap.incident.status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                continue

            signals: list[MatchSignal] = []
            conflicts: list[str] = []
            suggested_link_type = IncidentLinkType.POSSIBLE_DUPLICATE

            # 1. Contact / Phone matching
            snap_phones = set()
            for r in snap.reports:
                p = extract_phone(r)
                if p:
                    snap_phones.add(p)

            if report_phone and snap_phones:
                if report_phone in snap_phones:
                    signals.append(MatchSignal(
                        name="phone_match",
                        weight=0.35,
                        score=1.0,
                        detail=f"Exact phone match: {report_phone}",
                    ))
                else:
                    signals.append(MatchSignal(
                        name="phone_match",
                        weight=0.20,
                        score=0.0,
                        detail=f"Differing phone numbers (report: {report_phone}, incident: {', '.join(snap_phones)})",
                    ))
            else:
                signals.append(MatchSignal(
                    name="phone_match",
                    weight=0.05,
                    score=0.5,
                    detail="Phone number unknown on report or incident",
                ))

            # 2. Spatial proximity
            best_distance: Optional[float] = None
            snap_coords_list: list[PointCoordinates] = []

            # Prioritize confirmed / verified hypotheses
            for h in snap.hypotheses:
                if h.verification_status != VerificationStatus.REJECTED:
                    snap_coords_list.append(h.coordinates)

            # Fallback to coordinates on linked reports
            if not snap_coords_list:
                for r in snap.reports:
                    rc = extract_reported_position(r)
                    if rc:
                        snap_coords_list.append(rc)

            if report_coords and snap_coords_list:
                distances = [report_coords.distance_to(sc) for sc in snap_coords_list]
                best_distance = min(distances)

                if best_distance <= 30.0:
                    spatial_score = 1.0
                    detail = f"Immediate spatial proximity: {best_distance:.1f}m (<=30m)"
                elif best_distance <= 100.0:
                    spatial_score = 0.85
                    detail = f"Close spatial proximity: {best_distance:.1f}m (<=100m)"
                elif best_distance <= 250.0:
                    spatial_score = 0.60
                    detail = f"Moderate spatial proximity: {best_distance:.1f}m (<=250m)"
                elif best_distance <= 500.0:
                    spatial_score = 0.30
                    detail = f"Weak spatial proximity: {best_distance:.1f}m (<=500m)"
                else:
                    spatial_score = 0.0
                    detail = f"Distant location: {best_distance:.1f}m (>500m)"

                signals.append(MatchSignal(
                    name="spatial_proximity",
                    weight=0.35,
                    score=spatial_score,
                    detail=detail,
                ))
            else:
                signals.append(MatchSignal(
                    name="spatial_proximity",
                    weight=0.05,
                    score=0.5,
                    detail="Coordinates unknown on report or incident",
                ))

            # 3. Name / Household matching
            snap_names = set()
            for r in snap.reports:
                nm = extract_name(r)
                if nm:
                    snap_names.add(nm.lower())

            if report_name and snap_names:
                r_lower = report_name.lower()
                if any(r_lower in sn or sn in r_lower for sn in snap_names):
                    signals.append(MatchSignal(
                        name="household_member_match",
                        weight=0.15,
                        score=1.0,
                        detail=f"Matching name: {report_name}",
                    ))
                else:
                    signals.append(MatchSignal(
                        name="household_member_match",
                        weight=0.10,
                        score=0.2,
                        detail=f"Differing names (report: {report_name})",
                    ))
            else:
                signals.append(MatchSignal(
                    name="household_member_match",
                    weight=0.05,
                    score=0.5,
                    detail="Name/household not provided",
                ))

            # 4. Evidence Corroboration & Contradiction Detection
            snap_item_ids = {item.id for item in snap.evidence_items}
            combined_items = evidence_items + snap.evidence_items

            if snap.evidence_items and evidence_items:
                contradictions = self._detector.detect_contradictions(combined_items)
                cross_contradictions = [
                    c for c in contradictions
                    if any(item_id in report_item_ids for item_id in c.evidence_item_ids)
                    and any(item_id in snap_item_ids for item_id in c.evidence_item_ids)
                ]

                corroborations = self._detector.detect_corroborations(combined_items)
                cross_corroborations = [
                    c for c in corroborations
                    if any(item_id in report_item_ids for item_id in c.evidence_item_ids)
                    and any(item_id in snap_item_ids for item_id in c.evidence_item_ids)
                ]

                has_severe = any(c.severity == "high" for c in cross_contradictions)
                for c in cross_contradictions:
                    conflicts.append(f"[{c.severity.upper()}] {c.attribute} ({c.conflict_type}): {c.description}")

                if has_severe:
                    suggested_link_type = IncidentLinkType.CONFLICTING
                    signals.append(MatchSignal(
                        name="evidence_contradiction",
                        weight=0.40,
                        score=0.0,
                        detail=f"Severe contradictions detected ({len(cross_contradictions)} conflicts)",
                    ))
                elif cross_contradictions:
                    suggested_link_type = IncidentLinkType.CONFLICTING
                    signals.append(MatchSignal(
                        name="evidence_contradiction",
                        weight=0.25,
                        score=0.2,
                        detail=f"Medium contradictions detected ({len(cross_contradictions)} conflicts)",
                    ))
                elif cross_corroborations:
                    signals.append(MatchSignal(
                        name="evidence_corroboration",
                        weight=0.15,
                        score=1.0,
                        detail=f"Corroborating evidence facts ({len(cross_corroborations)} items)",
                    ))
                else:
                    signals.append(MatchSignal(
                        name="evidence_facts",
                        weight=0.05,
                        score=0.5,
                        detail="No conflicting or corroborating evidence items",
                    ))
            else:
                signals.append(MatchSignal(
                    name="evidence_facts",
                    weight=0.05,
                    score=0.5,
                    detail="Insufficient evidence items to cross-verify",
                ))

            # Composite scoring (weighted average)
            total_weight = sum(s.weight for s in signals)
            if total_weight > 0:
                raw_score = sum(s.weight * s.score for s in signals) / total_weight
            else:
                raw_score = 0.0

            # Conservative penalty for contradictions
            if conflicts:
                # Strictly cap score if contradictions exist
                raw_score = min(raw_score, 0.50)

            composite_score = round(max(0.0, min(1.0, raw_score)), 4)

            candidates.append(IncidentCandidate(
                incident_id=snap.incident.id,
                score=composite_score,
                signals=signals,
                conflicts=conflicts,
                spatial_distance_m=best_distance,
                suggested_link_type=suggested_link_type,
            ))

        # Sort descending by composite score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def _candidate_incident_ids(self, report: Report, session: Session) -> list[uuid.UUID]:
        """Open incidents that could plausibly describe the same situation.

        A report is compared only with incidents that share its phone number,
        have a position within CANDIDATE_RADIUS_M of the report's position, or
        were opened recently. This bounds the work per report regardless of
        how many incidents the operation has accumulated.
        """
        from sqlalchemy import text as sql

        params: dict[str, Any] = {
            "disaster_id": report.disaster_id,
            "recent_hours": RECENT_WINDOW_HOURS,
            "recent_limit": RECENT_LIMIT,
            "cap": MAX_CANDIDATE_INCIDENTS,
        }
        clauses = [
            """
            (SELECT id FROM incidents
             WHERE disaster_id = :disaster_id AND status NOT IN ('resolved','closed','duplicate')
               AND created_at > now() - make_interval(hours => :recent_hours)
             ORDER BY created_at DESC LIMIT :recent_limit)
            """
        ]
        phone = extract_phone(report)
        if phone:
            params["phone"] = phone
            clauses.append(
                """
                (SELECT ir.incident_id FROM incident_reports ir
                 JOIN reports r ON r.id = ir.report_id
                 WHERE r.disaster_id = :disaster_id
                   AND right(regexp_replace(coalesce(r.caller_contact, r.source_identity, ''), '\\D', '', 'g'), 10) = :phone)
                """
            )
        coords = extract_reported_position(report)
        if coords:
            params.update(lat=coords.latitude, lon=coords.longitude, radius=CANDIDATE_RADIUS_M)
            clauses.append(
                """
                (SELECT incident_id FROM location_hypotheses
                 WHERE verification_status <> 'rejected'
                   AND ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius))
                """
            )
        rows = session.execute(
            sql(
                f"""
                SELECT i.id FROM incidents i
                WHERE i.id IN ({" UNION ".join(clauses)})
                  AND i.disaster_id = :disaster_id
                  AND i.status NOT IN ('resolved','closed','duplicate')
                ORDER BY i.created_at DESC
                LIMIT :cap
                """
            ),
            params,
        ).all()
        return [row.id for row in rows]

    def _load_snapshots_from_db(
        self,
        report: Report,
        session: Session,
    ) -> list[IncidentSnapshot]:
        """Load candidate incidents with their locations, reports and evidence in four queries."""
        from collections import defaultdict

        from sqlalchemy.orm import selectinload

        from raahat.domain.incidents.incident import Incident as DomainIncident
        from raahat.domain.reports.report import Report as DomainReport
        from raahat.infrastructure.database.models.evidence import EvidenceItemModel
        from raahat.infrastructure.database.models.incident import (
            IncidentModel,
            IncidentReportModel,
        )
        from raahat.infrastructure.database.models.location import LocationHypothesisModel
        from raahat.infrastructure.database.models.report import ReportModel
        from raahat.infrastructure.database.repositories.evidence import model_to_evidence_item
        from raahat.infrastructure.database.repositories.location_hypothesis import parse_wkb_point

        ids = self._candidate_incident_ids(report, session)
        if not ids:
            return []
        incident_models = session.scalars(
            select(IncidentModel).where(IncidentModel.id.in_(ids))
        ).all()

        hypotheses: dict[uuid.UUID, list[LocationHypothesis]] = defaultdict(list)
        for h_m in session.scalars(
            select(LocationHypothesisModel).where(LocationHypothesisModel.incident_id.in_(ids))
        ).all():
            hypotheses[h_m.incident_id].append(
                LocationHypothesis(
                    id=h_m.id,
                    incident_id=h_m.incident_id,
                    coordinates=parse_wkb_point(h_m.location),
                    candidate_label=h_m.candidate_label,
                    source_evidence_id=h_m.source_evidence_id,
                    probability=h_m.probability,
                    uncertainty_radius_m=h_m.uncertainty_radius_m,
                    verification_status=VerificationStatus(h_m.verification_status),
                    created_at=h_m.created_at,
                )
            )

        reports: dict[uuid.UUID, list[DomainReport]] = defaultdict(list)
        incident_of_report: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        for incident_id, r_m in session.execute(
            select(IncidentReportModel.incident_id, ReportModel)
            .join(ReportModel, IncidentReportModel.report_id == ReportModel.id)
            .where(IncidentReportModel.incident_id.in_(ids))
        ).all():
            try:
                s_type = SourceType(r_m.source_type)
            except ValueError:
                s_type = SourceType.WEB
            try:
                p_stat = ProcessingStatus(r_m.processing_status)
            except ValueError:
                p_stat = ProcessingStatus.PROCESSED
            reports[incident_id].append(
                DomainReport(
                    id=r_m.id,
                    disaster_id=r_m.disaster_id,
                    source_type=s_type,
                    source_event_id=r_m.source_event_id,
                    source_identity=r_m.source_identity or r_m.caller_contact,
                    device_id=r_m.device_id,
                    channel_reference=r_m.channel_reference,
                    raw_payload=dict(r_m.raw_payload),
                    received_at=r_m.received_at,
                    client_created_at=r_m.client_created_at,
                    language_code=r_m.language_code,
                    processing_status=p_stat,
                    idempotency_key=r_m.idempotency_key,
                )
            )
            incident_of_report[r_m.id].append(incident_id)

        evidence: dict[uuid.UUID, list[EvidenceItem]] = defaultdict(list)
        if incident_of_report:
            for ev_m in session.scalars(
                select(EvidenceItemModel)
                .options(selectinload(EvidenceItemModel.spans))
                .where(EvidenceItemModel.report_id.in_(list(incident_of_report)))
            ).all():
                item = model_to_evidence_item(ev_m)
                for incident_id in incident_of_report[ev_m.report_id]:
                    evidence[incident_id].append(item)

        snapshots: list[IncidentSnapshot] = []
        for inc_m in incident_models:
            snapshots.append(
                IncidentSnapshot(
                    incident=DomainIncident(
                        id=inc_m.id,
                        disaster_id=inc_m.disaster_id,
                        status=IncidentStatus(inc_m.status),
                        operational_priority=PriorityLevel(inc_m.operational_priority),
                        severity_facts=dict(inc_m.severity_facts or {}),
                        last_confirmed_at=inc_m.last_confirmed_at,
                        created_at=inc_m.created_at,
                        updated_at=inc_m.updated_at,
                    ),
                    hypotheses=hypotheses[inc_m.id],
                    reports=reports[inc_m.id],
                    evidence_items=evidence[inc_m.id],
                )
            )
        return snapshots
