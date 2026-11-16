"""Geospatial service adapters: Nominatim geocoding, OSRM routing, Overpass landmark export.

All three serve OpenStreetMap data (ODbL). The public Nominatim and Overpass
instances have usage policies: identify the application, stay at or below one
request per second, no bulk use. The public OSRM demo server is for
demonstration only; operational routing needs a self-hosted instance.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from .base import ProviderError, ProviderNotConfigured, Stopwatch, translate_http_errors


@dataclass(frozen=True)
class GeocodeCandidate:
    label: str
    latitude: float
    longitude: float
    # Nominatim's relative importance (0-1). A ranking hint, not a probability.
    importance: Optional[float]
    kind: Optional[str]
    osm_ref: Optional[str]
    bounding_radius_m: Optional[float]


@dataclass(frozen=True)
class GeocodeResult:
    query: str
    candidates: tuple[GeocodeCandidate, ...]
    provider: str
    duration_ms: float


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6_371_008.8 * asin(sqrt(a))


class NominatimClient:
    name = "nominatim"

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        user_agent: str,
        country_codes: str = "in",
        timeout_seconds: float = 15.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._country_codes = country_codes
        self._timeout = timeout_seconds
        self._transport = transport
        self._lock = threading.Lock()
        self._last_call = 0.0

    @property
    def configured(self) -> bool:
        return self._enabled

    def _throttle(self) -> None:
        # Usage policy: at most one request per second.
        with self._lock:
            wait = 1.0 - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        viewbox: Optional[tuple[float, float, float, float]] = None,
    ) -> GeocodeResult:
        """Search for a place. ``viewbox`` is (min_lon, min_lat, max_lon, max_lat) and biases results."""
        if not self._enabled:
            raise ProviderNotConfigured(self.name, "GEOCODER_PROVIDER")
        query = query.strip()
        if not query:
            raise ProviderError(self.name, "empty query")
        params: dict[str, Any] = {
            "q": query,
            "format": "jsonv2",
            "limit": max(1, min(limit, 10)),
            "addressdetails": 0,
        }
        if self._country_codes:
            params["countrycodes"] = self._country_codes
        if viewbox is not None:
            params["viewbox"] = ",".join(f"{v:.5f}" for v in viewbox)
        self._throttle()
        watch = Stopwatch()
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/search",
                    params=params,
                    headers={"User-Agent": self._user_agent, "Accept-Language": "en"},
                )
                response.raise_for_status()
        try:
            rows = response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "response was not JSON") from exc
        if not isinstance(rows, list):
            raise ProviderError(self.name, "unexpected response shape")

        candidates: list[GeocodeCandidate] = []
        for row in rows:
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            radius: Optional[float] = None
            box = row.get("boundingbox")
            if isinstance(box, list) and len(box) == 4:
                try:
                    south, north, west, east = (float(v) for v in box)
                    radius = round(_haversine_m(south, west, north, east) / 2, 1)
                except (TypeError, ValueError):
                    radius = None
            importance = row.get("importance")
            osm_type, osm_id = row.get("osm_type"), row.get("osm_id")
            candidates.append(
                GeocodeCandidate(
                    label=str(row.get("display_name") or query),
                    latitude=lat,
                    longitude=lon,
                    importance=float(importance) if isinstance(importance, (int, float)) else None,
                    kind=str(row.get("type")) if row.get("type") else None,
                    osm_ref=f"{osm_type}/{osm_id}" if osm_type and osm_id else None,
                    bounding_radius_m=radius,
                )
            )
        return GeocodeResult(
            query=query,
            candidates=tuple(candidates),
            provider=self.name,
            duration_ms=watch.elapsed_ms,
        )

    def probe(self) -> float:
        """Check reachability with the status endpoint. Returns latency in ms."""
        if not self._enabled:
            raise ProviderNotConfigured(self.name, "GEOCODER_PROVIDER")
        self._throttle()
        watch = Stopwatch()
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/status",
                    params={"format": "json"},
                    headers={"User-Agent": self._user_agent},
                )
                response.raise_for_status()
        return watch.elapsed_ms


@dataclass(frozen=True)
class RouteEstimate:
    distance_m: float
    duration_s: float
    geometry: list[tuple[float, float]]  # (lat, lon) pairs
    provider: str
    profile: str
    duration_ms: float


class OsrmClient:
    name = "osrm"

    def __init__(
        self,
        *,
        base_url: Optional[str],
        profile: str = "driving",
        timeout_seconds: float = 15.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self.profile = profile
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    def route(
        self, *, origin: tuple[float, float], destination: tuple[float, float]
    ) -> RouteEstimate:
        """Road route between two (lat, lon) points.

        The result reflects the road network in the routing server's data
        extract. It does not know about flooding or closures.
        """
        if not self._base_url:
            raise ProviderNotConfigured(self.name, "OSRM_BASE_URL")
        coords = f"{origin[1]:.6f},{origin[0]:.6f};{destination[1]:.6f},{destination[0]:.6f}"
        watch = Stopwatch()
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.get(
                    f"{self._base_url}/route/v1/{self.profile}/{coords}",
                    params={"overview": "simplified", "geometries": "geojson"},
                )
                response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "response was not JSON") from exc
        if body.get("code") != "Ok" or not body.get("routes"):
            raise ProviderError(self.name, f"no route found ({body.get('code', 'unknown')})")
        route = body["routes"][0]
        try:
            geometry = [(float(lat), float(lon)) for lon, lat in route["geometry"]["coordinates"]]
            return RouteEstimate(
                distance_m=float(route["distance"]),
                duration_s=float(route["duration"]),
                geometry=geometry,
                provider=self.name,
                profile=self.profile,
                duration_ms=watch.elapsed_ms,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(self.name, "unexpected route shape") from exc

    def probe(self) -> float:
        if not self._base_url:
            raise ProviderNotConfigured(self.name, "OSRM_BASE_URL")
        # Two points 1 km apart in central Kochi: a minimal real routing query.
        estimate = self.route(origin=(9.9816, 76.2999), destination=(9.9720, 76.2850))
        return estimate.duration_ms


@dataclass(frozen=True)
class OsmLandmark:
    osm_ref: str
    name: str
    kind: str
    latitude: float
    longitude: float
    alt_names: tuple[str, ...]
    tags: dict[str, str]


# OSM keys whose named features make useful verbal landmarks, mapped to a kind.
LANDMARK_SELECTORS: tuple[tuple[str, str, str], ...] = (
    ("amenity", "hospital|clinic|doctors", "medical"),
    ("amenity", "school|college|university", "education"),
    ("amenity", "place_of_worship", "place_of_worship"),
    ("amenity", "police|fire_station", "emergency_service"),
    ("amenity", "bus_station|ferry_terminal", "transport"),
    ("amenity", "townhall|community_centre|post_office|bank|marketplace", "civic"),
    ("railway", "station|halt", "transport"),
    ("man_made", "bridge", "bridge"),
    ("place", "village|suburb|neighbourhood|hamlet|town", "locality"),
)


class OverpassClient:
    name = "overpass"

    def __init__(
        self,
        *,
        base_url: str = "https://overpass-api.de/api/interpreter",
        user_agent: str,
        timeout_seconds: float = 120.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = base_url
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._transport = transport

    @staticmethod
    def build_query(bbox: tuple[float, float, float, float], timeout: int = 90) -> str:
        """Overpass QL for named landmark features in (south, west, north, east)."""
        south, west, north, east = bbox
        area = f"({south:.5f},{west:.5f},{north:.5f},{east:.5f})"
        clauses = "".join(
            f'nwr["{key}"~"^({values})$"]["name"]{area};' for key, values, _ in LANDMARK_SELECTORS
        )
        return f"[out:json][timeout:{timeout}];({clauses});out center tags;"

    def fetch_landmarks(self, bbox: tuple[float, float, float, float]) -> list[OsmLandmark]:
        south, west, north, east = bbox
        if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
            raise ProviderError(self.name, "bounding box must be south,west,north,east")
        if (north - south) * (east - west) > 1.0:
            raise ProviderError(
                self.name, "bounding box larger than 1 square degree; import in smaller tiles"
            )
        with translate_http_errors(self.name):
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    self._base_url,
                    data={"data": self.build_query(bbox)},
                    headers={"User-Agent": self._user_agent},
                )
                response.raise_for_status()
        try:
            elements = response.json()["elements"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(self.name, "unexpected response shape") from exc

        landmarks: list[OsmLandmark] = []
        for el in elements:
            tags = el.get("tags") or {}
            name = tags.get("name:en") or tags.get("name")
            if not name:
                continue
            lat = el.get("lat", (el.get("center") or {}).get("lat"))
            lon = el.get("lon", (el.get("center") or {}).get("lon"))
            if lat is None or lon is None:
                continue
            kind = "other"
            for key, values, mapped in LANDMARK_SELECTORS:
                if tags.get(key) in values.split("|"):
                    kind = mapped
                    break
            alt = {
                tags[k]
                for k in ("name", "name:en", "name:ml", "name:hi", "name:kok", "alt_name", "old_name")
                if tags.get(k) and tags[k] != name
            }
            landmarks.append(
                OsmLandmark(
                    osm_ref=f"{el.get('type')}/{el.get('id')}",
                    name=str(name)[:255],
                    kind=kind,
                    latitude=float(lat),
                    longitude=float(lon),
                    alt_names=tuple(sorted(alt)),
                    tags={k: str(v) for k, v in tags.items() if k in _KEPT_TAGS},
                )
            )
        return landmarks


_KEPT_TAGS = frozenset(
    {"amenity", "railway", "man_made", "place", "religion", "denomination", "operator", "addr:city", "addr:district"}
)
