"""Integration tests for state and district-scoped authentication routes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from raahat.api.app import app

# ---------------------------------------------------------------------------
# Reference: expected passwords derived from the production formula
# _clean_name_for_password("Kerala")[:8]       = "Kerala"
# _clean_name_for_password("Ernakulam")[:10]   = "Ernakulam"  (parenthetical dropped)
# → district password = "KeralaErnakulam2026#"
#
# _clean_name_for_password("Maharashtra")[:12] = "Maharashtra"
# → SEOC password = "MaharashtraSEOC2026#"
# ---------------------------------------------------------------------------
_KL_EKM_PASSWORD = "KeralaErnakulam2026#"
_MH_SEOC_PASSWORD = "MaharashtraSEOC2026#"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_auth_states_list(client: TestClient) -> None:
    """Verify listing all 36 Indian states and UTs."""
    res = client.get("/api/v1/auth/states")
    assert res.status_code == 200
    states = res.json()
    assert len(states) == 36
    codes = {s["code"] for s in states}
    assert "KL" in codes
    assert "MH" in codes
    assert "OD" in codes
    assert "DL" in codes


def test_auth_jurisdictions_hierarchy(client: TestClient) -> None:
    """Verify jurisdictions return districts and GPS centroids."""
    res = client.get("/api/v1/auth/jurisdictions")
    assert res.status_code == 200
    data = res.json()
    kerala = next((s for s in data if s["code"] == "KL"), None)
    assert kerala is not None
    assert kerala["name"] == "Kerala"
    assert kerala["lat"] > 8.0 and kerala["lng"] > 75.0
    assert len(kerala["districts"]) >= 10
    ernakulam = next((d for d in kerala["districts"] if "EKM" in d["code"]), None)
    assert ernakulam is not None
    assert "Ernakulam" in ernakulam["name"]
    assert ernakulam["lat"] > 9.0


def test_auth_jurisdictions_goa_has_two_districts(client: TestClient) -> None:
    """Goa must have both North Goa and South Goa districts."""
    res = client.get("/api/v1/auth/jurisdictions")
    assert res.status_code == 200
    data = res.json()
    goa = next((s for s in data if s["code"] == "GA"), None)
    assert goa is not None
    assert len(goa["districts"]) == 2
    district_names = " ".join(d["name"] for d in goa["districts"])
    assert "North" in district_names
    assert "South" in district_names


def test_auth_login_district_success(client: TestClient) -> None:
    """Verify district DEOC operator login with the correct derived passkey."""
    payload = {
        "state_code": "KL",
        "district_code": "KL-EKM",
        "password": _KL_EKM_PASSWORD,
        "officer_name": "Capt. Rajesh Nair",
    }
    res = client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["state_code"] == "KL"
    assert body["state_name"] == "Kerala"
    assert body["district_code"] == "KL-EKM"
    assert "Ernakulam" in body["district_name"]
    assert body["role"] == "DDMA_DEOC_COMMANDER"
    assert body["officer_name"] == "Capt. Rajesh Nair"
    assert body["access_token"]

    # Verify /auth/me with Bearer token
    token = body["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["sub"] == "ddma:KL:KL-EKM"
    assert me_data["district_code"] == "KL-EKM"


def test_auth_login_state_headquarters_success(client: TestClient) -> None:
    """Verify state-level SEOC command login without district scope."""
    payload = {
        "state_code": "MH",
        "password": _MH_SEOC_PASSWORD,
    }
    res = client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["state_code"] == "MH"
    assert body["state_name"] == "Maharashtra"
    assert body["district_code"] is None
    assert body["role"] == "SDMA_SEOC_COMMANDER"


def test_auth_login_invalid_password(client: TestClient) -> None:
    """Verify invalid password returns 401 Unauthorized."""
    payload = {
        "state_code": "KL",
        "password": "totally_wrong_pass_xyz",
    }
    res = client.post("/api/v1/auth/login", json=payload)
    assert res.status_code == 401
    # Error message must be generic — never disclose which field failed
    assert res.json()["detail"] == "Invalid credentials"


def test_auth_login_demo_passwords_rejected(client: TestClient) -> None:
    """Verify legacy demo passwords are no longer accepted.

    Uses Odisha (OD) to avoid cross-test interference with KL rate-limit state.
    Both 401 (wrong password) and 429 (rate-limited) confirm the password was not
    accepted — the endpoint returned an error either way.
    """
    for bad_pw in ("raahat2026", "admin", "demo123", "ndrf123", "dispatcher"):
        payload = {"state_code": "OD", "password": bad_pw}
        res = client.post("/api/v1/auth/login", json=payload)
        assert res.status_code in (401, 429), (
            f"Demo password '{bad_pw}' was accepted (status {res.status_code})"
        )


def test_auth_rate_limit_triggers(client: TestClient) -> None:
    """Verify brute-force protection triggers 429 after repeated failures."""
    # TestClient uses 127.0.0.1 as remote IP; we need to exhaust its window.
    # Rate limit is 5 failures per 15 minutes.
    bad_payload = {"state_code": "KL", "password": "definitely_wrong_1"}
    responses = [
        client.post("/api/v1/auth/login", json=bad_payload)
        for _ in range(6)
    ]
    status_codes = [r.status_code for r in responses]
    # First 5 should be 401 (or 429 if already limited from prior test),
    # 6th must be 429.
    assert responses[-1].status_code == 429, (
        f"Expected 429 on 6th attempt, got {responses[-1].status_code}. "
        f"All codes: {status_codes}"
    )


def test_auth_credential_format_endpoint(client: TestClient) -> None:
    """Verify the credential-format hint endpoint returns expected keys."""
    res = client.get("/api/v1/auth/credential-format")
    assert res.status_code == 200
    body = res.json()
    assert "deoc_format" in body
    assert "seoc_format" in body
    assert "example_deoc" in body
    assert "example_seoc" in body
    assert "KeralaErnakulam" in body["example_deoc"]
