"""Response and request models shared across routers."""
from __future__ import annotations

from typing import Generic, Optional, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Pagination:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> None:
        self.limit = limit
        self.offset = offset


class Coordinates(BaseModel):
    latitude: float
    longitude: float


def coordinates_or_none(latitude: Optional[float], longitude: Optional[float]) -> Optional[Coordinates]:
    if latitude is None or longitude is None:
        return None
    return Coordinates(latitude=float(latitude), longitude=float(longitude))


def split_csv(raw: Optional[str]) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]
