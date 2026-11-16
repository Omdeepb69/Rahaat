"""Incident lifecycle: which status changes are allowed, and by what kind of action.

The table is the single definition of the state machine. Services call
``ensure_transition`` before changing status; nothing else writes the column.
"""
from __future__ import annotations

from raahat.domain.shared.enums import IncidentStatus

S = IncidentStatus

ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    S.UNVERIFIED: frozenset({S.UNDER_REVIEW, S.VERIFIED, S.CLOSED, S.DUPLICATE}),
    S.UNDER_REVIEW: frozenset({S.UNVERIFIED, S.VERIFIED, S.CLOSED, S.DUPLICATE}),
    S.VERIFIED: frozenset(
        {S.UNDER_REVIEW, S.ASSIGNED, S.RESOLVED, S.CLOSED, S.DUPLICATE}
    ),
    S.ASSIGNED: frozenset({S.VERIFIED, S.IN_PROGRESS, S.RESOLVED, S.CLOSED}),
    S.IN_PROGRESS: frozenset({S.ASSIGNED, S.VERIFIED, S.RESOLVED}),
    S.RESOLVED: frozenset({S.VERIFIED, S.CLOSED}),
    S.CLOSED: frozenset({S.UNDER_REVIEW}),
    # A duplicate is restored only by reversing the merge that produced it.
    S.DUPLICATE: frozenset({S.UNVERIFIED, S.UNDER_REVIEW, S.VERIFIED}),
}

# Statuses in which the incident still needs attention.
OPEN_STATUSES: frozenset[IncidentStatus] = frozenset(
    {S.UNVERIFIED, S.UNDER_REVIEW, S.VERIFIED, S.ASSIGNED, S.IN_PROGRESS}
)
# Statuses in which a resource may be committed. Dispatch requires that a
# person has verified the incident first.
DISPATCHABLE_STATUSES: frozenset[IncidentStatus] = frozenset(
    {S.VERIFIED, S.ASSIGNED, S.IN_PROGRESS}
)
# Statuses an operator may set directly. ASSIGNED and IN_PROGRESS follow from
# assignment activity; DUPLICATE follows from a reviewed merge.
OPERATOR_SETTABLE: frozenset[IncidentStatus] = frozenset(
    {S.UNVERIFIED, S.UNDER_REVIEW, S.VERIFIED, S.RESOLVED, S.CLOSED}
)

CLOSURE_REASONS = (
    "resolved",
    "false_report",
    "no_action_required",
    "handled_elsewhere",
    "other",
)


class InvalidTransitionError(ValueError):
    def __init__(self, current: IncidentStatus, target: IncidentStatus) -> None:
        self.current = current
        self.target = target
        allowed = ", ".join(sorted(s.value for s in ALLOWED_TRANSITIONS[current])) or "none"
        super().__init__(
            f"An incident that is '{current.value}' cannot become '{target.value}'. "
            f"Allowed: {allowed}."
        )


def can_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def ensure_transition(current: IncidentStatus, target: IncidentStatus) -> None:
    if current == target:
        raise InvalidTransitionError(current, target)
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
