"""Indian states and districts (LGD codes) and the jurisdiction an account covers.

Reference data is the Local Government Directory list bundled with the
package. Codes are LGD codes, which stay stable when a district is renamed.

An account's jurisdiction decides which operations it can see:

* national (no state): every operation;
* state: every operation whose state matches;
* district: only operations in that district.

An operation with no jurisdiction is visible to national accounts only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Optional

NATIONAL_USERNAME = "national"


@dataclass(frozen=True)
class District:
    code: str
    name: str
    state_code: str


@dataclass(frozen=True)
class State:
    code: str
    name: str
    kind: str
    districts: tuple[District, ...]


@dataclass(frozen=True)
class Directory:
    source: str
    licence: str
    observed_on: str
    states: tuple[State, ...]
    by_state: dict[str, State]
    by_district: dict[str, District]


@lru_cache(maxsize=1)
def directory() -> Directory:
    raw: dict[str, Any] = json.loads(
        resources.files("raahat.data").joinpath("jurisdictions.json").read_text(encoding="utf-8")
    )
    states: list[State] = []
    for s in raw["states"]:
        districts = tuple(District(d["code"], d["name"], s["code"]) for d in s["districts"])
        states.append(State(s["code"], s["name"], s["kind"], districts))
    return Directory(
        source=raw["source"],
        licence=raw["licence"],
        observed_on=raw["observed_on"],
        states=tuple(states),
        by_state={s.code: s for s in states},
        by_district={d.code: d for s in states for d in s.districts},
    )


class UnknownJurisdiction(ValueError):
    pass


@dataclass(frozen=True)
class Jurisdiction:
    state_code: Optional[str] = None
    district_code: Optional[str] = None

    @classmethod
    def validated(cls, state_code: Optional[str], district_code: Optional[str]) -> "Jurisdiction":
        """Check codes against the directory. A district must belong to the state."""
        ref = directory()
        state_code = (state_code or "").strip() or None
        district_code = (district_code or "").strip() or None
        if state_code is None:
            if district_code is not None:
                raise UnknownJurisdiction("A district needs its state")
            return cls()
        if state_code not in ref.by_state:
            raise UnknownJurisdiction("Unknown state")
        if district_code is not None:
            district = ref.by_district.get(district_code)
            if district is None or district.state_code != state_code:
                raise UnknownJurisdiction("That district is not in the selected state")
        return cls(state_code, district_code)

    @property
    def level(self) -> str:
        if self.state_code is None:
            return "national"
        return "district" if self.district_code else "state"

    @property
    def is_national(self) -> bool:
        return self.state_code is None

    @property
    def username(self) -> str:
        if self.state_code is None:
            return NATIONAL_USERNAME
        if self.district_code is None:
            return f"state-{self.state_code}"
        return f"district-{self.district_code}"

    @property
    def state_name(self) -> Optional[str]:
        state = directory().by_state.get(self.state_code or "")
        return state.name if state else None

    @property
    def district_name(self) -> Optional[str]:
        district = directory().by_district.get(self.district_code or "")
        return district.name if district else None

    @property
    def label(self) -> str:
        if self.state_code is None:
            return "National control room"
        if self.district_code is None:
            return f"{self.state_name} state control room"
        return f"{self.district_name} district control room, {self.state_name}"

    def covers(self, state_code: Optional[str], district_code: Optional[str]) -> bool:
        """Whether an operation with these codes falls inside this jurisdiction."""
        if self.state_code is None:
            return True
        if state_code != self.state_code:
            return False
        return self.district_code is None or district_code == self.district_code

    def sql(self, alias: str) -> tuple[str, dict[str, Any]]:
        """SQL condition limiting ``alias`` (a disasters row) to this jurisdiction."""
        if self.state_code is None:
            return "TRUE", {}
        if self.district_code is None:
            return f"{alias}.state_code = :scope_state", {"scope_state": self.state_code}
        return (
            f"({alias}.state_code = :scope_state AND {alias}.district_code = :scope_district)",
            {"scope_state": self.state_code, "scope_district": self.district_code},
        )
