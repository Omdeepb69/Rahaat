"""Priority score for ordering open incidents.

The score is an explicit sum of named terms so that the order of the queue can
be explained line by line. It orders work; it does not replace the triage
level, which remains the deterministic policy's output.

    score = level + people + conditions + waiting

* ``level``      triage level (critical 1000, urgent 600, unassessed 500,
                 standard 300, low 100). Unassessed ranks above standard:
                 unknown never lowers priority.
* ``people``     20 per person reported, capped at 20 people.
* ``conditions`` trapped +60, medical emergency +60, life-threatening +40,
                 vulnerable people +30, water rising +40.
* ``waiting``    2 per minute since the incident was created, capped at 180
                 minutes, so older incidents rise within and across adjacent
                 levels and nothing waits indefinitely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class PriorityWeights:
    level: dict[str, float]
    per_person: float = 20.0
    people_cap: int = 20
    trapped: float = 60.0
    medical: float = 60.0
    life_threatening: float = 40.0
    vulnerable: float = 30.0
    water_rising: float = 40.0
    per_waiting_minute: float = 2.0
    waiting_cap_minutes: float = 180.0


DEFAULT_WEIGHTS = PriorityWeights(
    level={
        "critical_review": 1000.0,
        "urgent": 600.0,
        "unassessed": 500.0,
        "standard": 300.0,
        "low": 100.0,
    }
)


@dataclass(frozen=True)
class ScoreTerm:
    name: str
    points: float
    detail: str


@dataclass(frozen=True)
class PriorityScore:
    total: float
    terms: tuple[ScoreTerm, ...]


def score_incident(
    *,
    priority: str,
    facts: dict[str, Any],
    created_at: datetime,
    now: Optional[datetime] = None,
    weights: PriorityWeights = DEFAULT_WEIGHTS,
) -> PriorityScore:
    now = now or datetime.now(timezone.utc)
    terms: list[ScoreTerm] = [
        ScoreTerm("level", weights.level.get(priority, weights.level["unassessed"]), f"triage level: {priority}")
    ]
    people = facts.get("people_count")
    if isinstance(people, int) and people > 0:
        counted = min(people, weights.people_cap)
        terms.append(ScoreTerm("people", counted * weights.per_person, f"{people} people reported"))
    else:
        terms.append(ScoreTerm("people", 0.0, "number of people unknown"))
    for key, points, label in (
        ("trapped_status", weights.trapped, "people trapped"),
        ("medical_emergency", weights.medical, "medical emergency"),
        ("is_life_threatening_medical", weights.life_threatening, "life-threatening condition"),
        ("vulnerable_present", weights.vulnerable, "vulnerable people present"),
    ):
        if facts.get(key) is True:
            terms.append(ScoreTerm(key, points, label))
    if facts.get("water_level_trend") == "rising":
        terms.append(ScoreTerm("water_rising", weights.water_rising, "water level rising"))
    waited = max(0.0, (now - created_at).total_seconds() / 60.0)
    counted_wait = min(waited, weights.waiting_cap_minutes)
    terms.append(
        ScoreTerm("waiting", round(counted_wait * weights.per_waiting_minute, 1), f"waiting {waited:.0f} min")
    )
    return PriorityScore(total=round(sum(t.points for t in terms), 1), terms=tuple(terms))
