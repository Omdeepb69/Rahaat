from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from raahat.application.dispatch import recommender
from raahat.application.dispatch.priority import score_incident
from raahat.domain.incidents.lifecycle import InvalidTransitionError, ensure_transition
from raahat.domain.shared.enums import IncidentStatus as S

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("current,target", [(S.UNVERIFIED, S.VERIFIED), (S.VERIFIED, S.ASSIGNED),
                                            (S.IN_PROGRESS, S.RESOLVED), (S.CLOSED, S.UNDER_REVIEW)])
def test_allowed_transitions(current, target):
    ensure_transition(current, target)


@pytest.mark.parametrize("current,target", [(S.UNVERIFIED, S.RESOLVED), (S.UNVERIFIED, S.ASSIGNED),
                                            (S.CLOSED, S.VERIFIED), (S.VERIFIED, S.VERIFIED),
                                            (S.IN_PROGRESS, S.CLOSED)])
def test_rejected_transitions(current, target):
    with pytest.raises(InvalidTransitionError):
        ensure_transition(current, target)


def test_priority_score_terms_and_unknown_never_lowers():
    trapped = score_incident(priority="critical_review", facts={"trapped_status": True, "people_count": 5},
                             created_at=NOW, now=NOW)
    assert {t.name for t in trapped.terms} >= {"level", "people", "trapped_status", "waiting"}
    assert trapped.total == 1000 + 100 + 60
    unassessed = score_incident(priority="unassessed", facts={}, created_at=NOW, now=NOW)
    standard = score_incident(priority="standard", facts={}, created_at=NOW, now=NOW)
    assert unassessed.total > standard.total
    old = score_incident(priority="standard", facts={}, created_at=NOW - timedelta(hours=10), now=NOW)
    assert old.total == standard.total + 360  # waiting capped at 180 min x 2


def _need(**facts):
    return recommender.IncidentNeed(
        id=uuid.uuid4(), reference="INC-T", priority="urgent", category=facts.pop("category", "flood"),
        facts=facts, created_at=NOW, position=(10.0, 76.3), location_status="confirmed",
    )


def _resource(callsign, capabilities, *, position=(10.01, 76.3), status="available", capacity=None,
              age_minutes=5):
    return recommender.ResourceState(
        id=uuid.uuid4(), callsign=callsign, name=callsign, resource_type="boat",
        capabilities=tuple(capabilities), status=status, capacity=capacity, position=position,
        position_updated_at=NOW - timedelta(minutes=age_minutes) if position else None,
        position_source="operator",
    )


def test_requirements_follow_facts():
    caps = lambda **f: [r.capability for r in recommender.required_capabilities(f, f.pop("category", "flood"))]  # noqa: E731
    assert caps(trapped_status=True, water_level_trend="rising") == ["water_rescue"]
    assert "medical" in caps(medical_emergency=True)
    assert caps(category="other") == []


def test_infeasible_resources_are_excluded_with_reasons():
    need = _need(trapped_status=True, water_level_trend="rising")
    result = recommender.recommend(need, [
        _resource("BOAT", ["water_rescue"]),
        _resource("AMB", ["medical"]),
        _resource("BOAT-2", ["water_rescue"], status="maintenance"),
    ], now=NOW)
    assert [c.callsign for c in result.candidates] == ["BOAT"]
    reasons = {e.callsign: e.reason for e in result.excluded}
    assert "required" in reasons["AMB"] and "maintenance" in reasons["BOAT-2"]


def test_nearer_and_fresher_resource_ranks_higher():
    need = _need(trapped_status=True, water_level_trend="rising", people_count=4)
    near = _resource("NEAR", ["water_rescue"], position=(10.005, 76.3), capacity=6)
    far = _resource("FAR", ["water_rescue"], position=(10.3, 76.3), capacity=6)
    stale = _resource("STALE", ["water_rescue"], position=(10.005, 76.3), capacity=6, age_minutes=300)
    result = recommender.recommend(need, [far, stale, near], now=NOW)
    assert [c.callsign for c in result.candidates] == ["NEAR", "STALE", "FAR"]
    assert any("old" in w for w in result.candidates[1].warnings)
    assert result.candidates[0].distance_basis == "straight_line"


def test_road_route_replaces_straight_line_when_supplied():
    need = _need(trapped_status=True, water_level_trend="rising")
    a = _resource("A", ["water_rescue"], position=(10.01, 76.3))
    b = _resource("B", ["water_rescue"], position=(10.02, 76.3))
    routes = {a.id: recommender.RouteInfo(30_000, 3600, "osrm"), b.id: recommender.RouteInfo(3_000, 400, "osrm")}
    result = recommender.recommend(need, [a, b], now=NOW, routes=routes)
    assert result.candidates[0].callsign == "B"
    assert result.candidates[0].distance_basis == "road_route"


def test_unknown_position_is_a_limitation_not_a_guess():
    need = recommender.IncidentNeed(id=uuid.uuid4(), reference="X", priority="urgent", category="flood",
                                    facts={"trapped_status": True}, created_at=NOW)
    result = recommender.recommend(need, [_resource("B", ["water_rescue"])], now=NOW)
    assert result.candidates[0].distance_m is None
    assert any("no established position" in limit for limit in result.limitations)


def test_plan_never_gives_one_resource_twice_and_serves_priority_first():
    first = _need(trapped_status=True, water_level_trend="rising")
    second = _need(trapped_status=True, water_level_trend="rising")
    boat = _resource("ONLY", ["water_rescue"])
    plan = recommender.plan([(first, 900.0), (second, 500.0)], [boat], now=NOW)
    assert plan[0].candidate is not None and plan[0].candidate.callsign == "ONLY"
    assert plan[1].candidate is None and plan[1].reason_unassigned
