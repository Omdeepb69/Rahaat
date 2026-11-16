"""Resource recommendation for an incident.

Pure functions over plain data: no database access, so the behaviour can be
tested and compared against baselines directly.

Objective
---------
For one incident, rank the resources that are *feasible* by a weighted score:

    score = 100 x (0.40 capability + 0.35 proximity + 0.15 capacity + 0.10 freshness)

* capability  fraction of the incident's required capabilities the resource has
* proximity   1 / (1 + distance / 10 km); road distance when a routing service
              supplied one, straight-line distance otherwise
* capacity    min(1, capacity / people) when both are known, else 0.5
* freshness   1 when the resource's position is at most 15 minutes old,
              falling linearly to 0 at 2 hours; 0 when it has no position

Feasibility (hard constraints): the resource is available, not retired, and —
when the incident has identifiable requirements — provides at least one of
them.

What this does not know: road closures, water depth along the route, crew
fatigue, fuel, or anything not recorded in the system. It produces a
recommendation for a person to accept, change or reject.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional, Sequence

WEIGHT_CAPABILITY = 0.40
WEIGHT_PROXIMITY = 0.35
WEIGHT_CAPACITY = 0.15
WEIGHT_FRESHNESS = 0.10
PROXIMITY_SCALE_M = 10_000.0
FRESH_MINUTES = 15.0
STALE_MINUTES = 120.0
ENGINE_VERSION = "2026.11"

OBJECTIVE = (
    "score = 100 x (0.40 capability match + 0.35 proximity + 0.15 capacity fit "
    "+ 0.10 position freshness), over available resources that provide at least "
    "one required capability"
)


@dataclass(frozen=True)
class IncidentNeed:
    id: uuid.UUID
    reference: str
    priority: str
    category: str
    facts: dict[str, Any]
    created_at: datetime
    position: Optional[tuple[float, float]] = None  # (lat, lon)
    location_status: str = "none"
    location_uncertainty_m: Optional[float] = None


@dataclass(frozen=True)
class ResourceState:
    id: uuid.UUID
    callsign: str
    name: str
    resource_type: str
    capabilities: tuple[str, ...]
    status: str
    capacity: Optional[int] = None
    position: Optional[tuple[float, float]] = None
    position_updated_at: Optional[datetime] = None
    position_source: Optional[str] = None
    is_retired: bool = False


@dataclass(frozen=True)
class Requirement:
    capability: str
    reason: str


@dataclass(frozen=True)
class Factor:
    name: str
    weight: float
    value: float  # 0..1
    contribution: float  # points out of 100
    detail: str


@dataclass(frozen=True)
class RouteInfo:
    distance_m: float
    duration_s: float
    provider: str


@dataclass(frozen=True)
class Candidate:
    resource_id: uuid.UUID
    callsign: str
    name: str
    resource_type: str
    score: float
    factors: tuple[Factor, ...]
    covered: tuple[str, ...]
    missing: tuple[str, ...]
    distance_m: Optional[float]
    # straight_line | road_route | unknown
    distance_basis: str
    travel_seconds: Optional[float]
    position_age_minutes: Optional[float]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Exclusion:
    resource_id: uuid.UUID
    callsign: str
    reason: str


@dataclass(frozen=True)
class Recommendation:
    incident_id: uuid.UUID
    requirements: tuple[Requirement, ...]
    candidates: tuple[Candidate, ...]
    excluded: tuple[Exclusion, ...]
    limitations: tuple[str, ...]
    objective: str = OBJECTIVE
    engine_version: str = ENGINE_VERSION
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def best(self) -> Optional[Candidate]:
        return self.candidates[0] if self.candidates else None


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = radians(a[0]), radians(a[1]), radians(b[0]), radians(b[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_008.8 * asin(sqrt(h))


def required_capabilities(facts: dict[str, Any], category: str) -> tuple[Requirement, ...]:
    """Derive what kind of help the recorded facts call for."""
    needs = {str(n) for n in (facts.get("relief_needs") or ())}
    hazards = {str(h) for h in (facts.get("hazards") or ())}
    depth = facts.get("water_depth_cm")
    trapped = facts.get("trapped_status") is True
    rising = facts.get("water_level_trend") == "rising"
    in_water = (
        category == "flood"
        or rising
        or facts.get("water_entering_occupied_floor") is True
        or (isinstance(depth, (int, float)) and depth >= 60)
    )
    found: dict[str, str] = {}

    if "rescue_boat" in needs:
        found["water_rescue"] = "a boat was requested"
    elif trapped and in_water:
        found["water_rescue"] = "people are trapped by water"
    if facts.get("medical_emergency") is True or "medical" in needs:
        found["medical"] = "a medical need was reported"
    if facts.get("is_life_threatening_medical") is True:
        found["patient_transport"] = "a life-threatening condition was reported"
    if trapped and not in_water:
        found["search_rescue"] = "people are trapped"
    if "structural_collapse" in hazards or "landslide" in hazards or category in (
        "landslide", "building_collapse",
    ):
        found.setdefault("search_rescue", "collapse or landslide reported")
    if "evacuation" in needs and "water_rescue" not in found:
        found["evacuation"] = "evacuation was requested"
    elif (
        "water_rescue" not in found
        and facts.get("water_entering_occupied_floor") is True
        and (rising or facts.get("vulnerable_present") is True)
    ):
        found["evacuation"] = "water is entering an occupied home"
    if "food_water" in needs:
        found["relief_supply"] = "food or drinking water was requested"
    if "shelter" in needs:
        found["shelter"] = "shelter was requested"
    return tuple(Requirement(c, r) for c, r in found.items())


def _freshness(age_minutes: Optional[float]) -> float:
    if age_minutes is None:
        return 0.0
    if age_minutes <= FRESH_MINUTES:
        return 1.0
    if age_minutes >= STALE_MINUTES:
        return 0.0
    return 1.0 - (age_minutes - FRESH_MINUTES) / (STALE_MINUTES - FRESH_MINUTES)


def _format_km(metres: float) -> str:
    return f"{metres / 1000:.1f} km" if metres >= 1000 else f"{metres:.0f} m"


def recommend(
    incident: IncidentNeed,
    resources: Sequence[ResourceState],
    *,
    now: Optional[datetime] = None,
    routes: Optional[dict[uuid.UUID, RouteInfo]] = None,
    limit: int = 10,
) -> Recommendation:
    now = now or datetime.now(timezone.utc)
    routes = routes or {}
    requirements = required_capabilities(incident.facts, incident.category)
    required = [r.capability for r in requirements]
    people = incident.facts.get("people_count")
    people = people if isinstance(people, int) and people > 0 else None

    limitations: list[str] = []
    if not requirements:
        limitations.append(
            "No specific need could be identified from the recorded facts, so every "
            "available resource is listed and capability is not a deciding factor."
        )
    if incident.position is None:
        limitations.append(
            "The incident has no established position, so distance is not part of the ranking."
        )
    elif incident.location_status != "confirmed":
        radius = (
            f" (assumed uncertainty {incident.location_uncertainty_m:.0f} m)"
            if incident.location_uncertainty_m
            else ""
        )
        limitations.append(
            f"The incident position is a candidate that no one has confirmed{radius}; "
            "distances are measured to that candidate."
        )
    if incident.position is not None and not routes:
        limitations.append(
            "No routing service is configured. Distances are straight-line and "
            "are shorter than any road or water route."
        )
    if people is None:
        limitations.append("The number of people is unknown, so capacity cannot be checked.")
    limitations.append(
        "Road closures, flooding along the route and crew condition are not known to the system."
    )

    candidates: list[Candidate] = []
    excluded: list[Exclusion] = []
    for res in resources:
        if res.is_retired:
            continue
        if res.status != "available":
            excluded.append(Exclusion(res.id, res.callsign, f"status is {res.status}"))
            continue
        covered = tuple(c for c in required if c in res.capabilities)
        missing = tuple(c for c in required if c not in res.capabilities)
        if required and not covered:
            excluded.append(
                Exclusion(res.id, res.callsign, "provides none of the required capabilities")
            )
            continue

        warnings: list[str] = []
        capability_value = (len(covered) / len(required)) if required else 1.0
        capability_detail = (
            f"provides {len(covered)} of {len(required)} required: {', '.join(covered)}"
            if required
            else "no specific requirement identified"
        )
        if missing:
            warnings.append(f"Does not provide: {', '.join(missing)}")

        age_minutes: Optional[float] = None
        if res.position_updated_at is not None:
            age_minutes = max(0.0, (now - res.position_updated_at).total_seconds() / 60.0)

        distance: Optional[float] = None
        basis = "unknown"
        travel: Optional[float] = None
        if incident.position is None:
            proximity_value, proximity_detail = 0.0, "incident position not established"
        elif res.position is None:
            proximity_value, proximity_detail = 0.0, "resource position not recorded"
            warnings.append("Position not recorded; distance unknown")
        else:
            route = routes.get(res.id)
            if route is not None:
                distance, basis, travel = route.distance_m, "road_route", route.duration_s
                proximity_detail = (
                    f"{_format_km(distance)} by road, about {travel / 60:.0f} min "
                    f"({route.provider}; does not account for closures)"
                )
            else:
                distance, basis = haversine_m(res.position, incident.position), "straight_line"
                proximity_detail = f"{_format_km(distance)} in a straight line"
            proximity_value = 1.0 / (1.0 + distance / PROXIMITY_SCALE_M)
            if age_minutes is not None and age_minutes > STALE_MINUTES:
                warnings.append(f"Position is {age_minutes / 60:.1f} h old and may be wrong")

        if people is not None and res.capacity is not None and res.capacity > 0:
            capacity_value = min(1.0, res.capacity / people)
            capacity_detail = f"capacity {res.capacity} for {people} people"
            if res.capacity < people:
                warnings.append(
                    f"Capacity {res.capacity} is below the {people} people reported"
                )
        else:
            capacity_value = 0.5
            capacity_detail = (
                "capacity not recorded" if res.capacity is None else "number of people unknown"
            )

        freshness_value = _freshness(age_minutes)
        freshness_detail = (
            "no position recorded"
            if age_minutes is None
            else f"position reported {age_minutes:.0f} min ago ({res.position_source or 'unknown source'})"
        )

        factors = tuple(
            Factor(name, weight, round(value, 3), round(100 * weight * value, 1), detail)
            for name, weight, value, detail in (
                ("capability", WEIGHT_CAPABILITY, capability_value, capability_detail),
                ("proximity", WEIGHT_PROXIMITY, proximity_value, proximity_detail),
                ("capacity", WEIGHT_CAPACITY, capacity_value, capacity_detail),
                ("freshness", WEIGHT_FRESHNESS, freshness_value, freshness_detail),
            )
        )
        candidates.append(
            Candidate(
                resource_id=res.id,
                callsign=res.callsign,
                name=res.name,
                resource_type=res.resource_type,
                score=round(sum(f.contribution for f in factors), 1),
                factors=factors,
                covered=covered,
                missing=missing,
                distance_m=round(distance, 1) if distance is not None else None,
                distance_basis=basis,
                travel_seconds=travel,
                position_age_minutes=round(age_minutes, 1) if age_minutes is not None else None,
                warnings=tuple(warnings),
            )
        )

    candidates.sort(
        key=lambda c: (-c.score, c.distance_m if c.distance_m is not None else float("inf"), c.callsign)
    )
    return Recommendation(
        incident_id=incident.id,
        requirements=requirements,
        candidates=tuple(candidates[:limit]),
        excluded=tuple(excluded),
        limitations=tuple(limitations),
        generated_at=now,
    )


@dataclass(frozen=True)
class PlanEntry:
    incident_id: uuid.UUID
    incident_reference: str
    priority_score: float
    candidate: Optional[Candidate]
    reason_unassigned: Optional[str]


def plan(
    incidents_by_priority: Sequence[tuple[IncidentNeed, float]],
    resources: Sequence[ResourceState],
    *,
    now: Optional[datetime] = None,
) -> list[PlanEntry]:
    """Propose one resource per incident, highest priority first.

    Greedy by priority score: the most urgent incident takes its best feasible
    resource, which is then unavailable to the rest. This is not a global
    optimum of total distance; it is the allocation that never gives a lower
    priority incident a resource a higher priority one would have ranked first.
    """
    remaining = list(resources)
    entries: list[PlanEntry] = []
    for incident, priority_score in incidents_by_priority:
        result = recommend(incident, remaining, now=now, limit=1)
        best = result.best
        if best is None:
            reason = (
                "no available resource provides a required capability"
                if result.requirements
                else "no resource is available"
            )
            entries.append(PlanEntry(incident.id, incident.reference, priority_score, None, reason))
            continue
        remaining = [r for r in remaining if r.id != best.resource_id]
        entries.append(PlanEntry(incident.id, incident.reference, priority_score, best, None))
    return entries
