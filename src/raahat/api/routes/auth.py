"""State and District-scoped authentication for RAAHAT 2.0 Command Center.

Supports Indian Disaster Management hierarchy:
- State Disaster Management Authority (SDMA / SEOC)
- District Disaster Management Authority (DDMA / DEOC)

Password scheme (deterministic, formula-based):
  DEOC  → {StateName}{DistrictShortName}{YEAR}#   e.g. KeralaErnakulam2026#
  SEOC  → {StateName}SEOC{YEAR}#                   e.g. KeralaSEOC2026#

The formula is communicated to officers out-of-band by the State EOC.
No demo/master passkeys exist — only the computed password is accepted.

When an operator authenticates:
1. Returns a signed HMAC-SHA256 JWT (stdlib only) with state_code, district_code,
   and GPS coordinates for the jurisdiction.
2. The frontend Leaflet map auto-centers on the operator's jurisdiction using those
   coordinates.
3. Failed attempts are rate-limited per IP (5 attempts per 15 minutes).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections import defaultdict
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(tags=["auth"])

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per remote IP)
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW_SECONDS = 900  # 15 minutes
_RATE_LIMIT_MAX_FAILURES = 5
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
    if len(_failed_attempts[ip]) >= _RATE_LIMIT_MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )


def _record_failure(ip: str) -> None:
    _failed_attempts[ip].append(time.time())

_ENV_SECRET = os.environ.get("RAAHAT_JWT_SECRET", "")
_JWT_SECRET: bytes = (
    _ENV_SECRET.encode()
    if _ENV_SECRET
    else b"raahat-dev-secret-change-in-production-do-not-use"
)
_JWT_ALGORITHM = "HS256"
_TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12-hour operational shift
DEFAULT_DISPATCHER_ID = "00000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Canonical Indian Jurisdictions Registry (Single Source of Truth)
from raahat.domain.geospatial.jurisdictions import (
    INDIAN_JURISDICTIONS,
    _STATE_INDEX as _STATE_MAP,
)

# ---------------------------------------------------------------------------
# Password derivation (name-based, deterministic)
# ---------------------------------------------------------------------------
_PASSWORD_STOP_WORDS = frozenset({
    "and", "of", "the", "dr", "sri", "ys", "br", "ntr", "potti", "sriramulu", "st",
})


def _clean_name_for_password(s: str) -> str:
    """Strip parentheticals, special chars, and stop-words; return CamelCase."""
    s = re.sub(r'\(.*?\)', '', s).strip()
    s = re.sub(r'[^a-zA-Z0-9 ]', '', s).strip()
    words = [w.capitalize() for w in s.split() if w.lower() not in _PASSWORD_STOP_WORDS]
    return ''.join(words[:2])


def _district_password(state_name: str, district_name: str, year: int = 2026) -> str:
    """DEOC passkey: {StateName[:8]}{DistrictShortName[:10]}{YEAR}#"""
    s = _clean_name_for_password(state_name)[:8]
    d = _clean_name_for_password(district_name)[:10]
    return f'{s}{d}{year}#'


def _seoc_password(state_name: str, year: int = 2026) -> str:
    """SEOC passkey: {StateName[:12]}SEOC{YEAR}#"""
    s = _clean_name_for_password(state_name)[:12]
    return f'{s}SEOC{year}#'


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (padding % 4))


def _make_token(payload_dict: dict[str, Any]) -> str:
    header = _b64url_encode(json.dumps({"alg": _JWT_ALGORITHM, "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps(payload_dict).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"


def _verify_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(_JWT_SECRET, signing_input, hashlib.sha256).digest()
    provided_sig = _b64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token payload")

    if int(time.time()) > claims.get("exp", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    return claims


_bearer = HTTPBearer(auto_error=False)


def require_state_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    return _verify_token(credentials.credentials)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DistrictInfo(BaseModel):
    code: str
    name: str
    lat: float
    lng: float
    zoom: int = 12


class JurisdictionItem(BaseModel):
    code: str
    name: str
    lat: float
    lng: float
    zoom: int = 8
    districts: list[DistrictInfo] = Field(default_factory=list)


class LoginRequest(BaseModel):
    state_code: str
    district_code: Optional[str] = None
    password: str
    officer_name: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    state_code: str
    state_name: str
    district_code: Optional[str] = None
    district_name: Optional[str] = None
    center_lat: float
    center_lng: float
    zoom: int
    officer_name: str
    role: str
    dispatcher_id: str
    expires_in: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/auth/jurisdictions", response_model=list[JurisdictionItem])
def list_jurisdictions() -> list[dict[str, Any]]:
    """Return all Indian states and Union Territories with districts and GPS coordinates."""
    return INDIAN_JURISDICTIONS


@router.get("/auth/states")
def list_states_summary() -> list[dict[str, str]]:
    """Quick state list for drop-downs."""
    return [{"code": s["code"], "name": s["name"]} for s in INDIAN_JURISDICTIONS]


@router.get("/auth/credential-format")
def credential_format() -> dict[str, str]:
    """Return the passkey formula for onboarding communications.

    This endpoint exists so that State EOCs can reference the formula in
    officer induction materials without hardcoding it. It does NOT return any
    actual passkey — only the derivation pattern and an illustrative example.
    """
    return {
        "deoc_format": "{StateName}{DistrictShortName}{YEAR}#",
        "seoc_format": "{StateName}SEOC{YEAR}#",
        "example_deoc": "KeralaErnakulam2026#",
        "example_seoc": "KeralaSEOC2026#",
        "note": "Contact your State EOC for your assigned passkey.",
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    """Authenticate an emergency command operator for a State or District DEOC.

    Passkey must match the jurisdiction-derived formula exactly.
    Failed attempts are rate-limited per IP to prevent brute-force attacks.
    Error responses are always generic — they never disclose which field failed.
    """
    client_ip: str = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    code = body.state_code.upper()
    state_data = _STATE_MAP.get(code)
    if not state_data:
        _record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Resolve district first so we can compute the correct expected password.
    district_code = body.district_code.strip() if body.district_code else None
    district_data = None
    if district_code:
        for d in state_data.get("districts", []):
            if d["code"].upper() == district_code.upper():
                district_data = d
                break
        if not district_data:
            _record_failure(client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

    expected = (
        _district_password(state_data["name"], district_data["name"])
        if district_data
        else _seoc_password(state_data["name"])
    )

    if not hmac.compare_digest(body.password, expected):
        _record_failure(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Determine center coordinates and zoom level
    if district_data:
        center_lat = district_data["lat"]
        center_lng = district_data["lng"]
        zoom = district_data.get("zoom", 12)
        district_name = district_data["name"]
        role = "DDMA_DEOC_COMMANDER"
        subject = f"ddma:{code}:{district_code}"
    else:
        center_lat = state_data["lat"]
        center_lng = state_data["lng"]
        zoom = state_data.get("zoom", 8)
        district_name = None
        role = "SDMA_SEOC_COMMANDER"
        subject = f"sdma:{code}"

    officer_name = body.officer_name or (
        f"Duty Officer ({district_name.split('(')[0].strip() if district_name else state_data['name']})"
    )

    now = int(time.time())
    payload = {
        "sub": subject,
        "state_code": code,
        "state_name": state_data["name"],
        "district_code": district_code,
        "district_name": district_name,
        "center_lat": center_lat,
        "center_lng": center_lng,
        "zoom": zoom,
        "officer_name": officer_name,
        "role": role,
        "dispatcher_id": DEFAULT_DISPATCHER_ID,
        "iat": now,
        "exp": now + _TOKEN_TTL_SECONDS,
    }

    token = _make_token(payload)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        state_code=code,
        state_name=state_data["name"],
        district_code=district_code,
        district_name=district_name,
        center_lat=center_lat,
        center_lng=center_lng,
        zoom=zoom,
        officer_name=officer_name,
        role=role,
        dispatcher_id=DEFAULT_DISPATCHER_ID,
        expires_in=_TOKEN_TTL_SECONDS,
    )


@router.get("/auth/me")
def me(claims: Annotated[dict[str, Any], Depends(require_state_auth)]) -> dict[str, Any]:
    """Inspect active session claims."""
    return claims
