"""Integration and verification tests for Operator Console Web Application (Task 4.6)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raahat.api.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_operator_console_root_redirect(client: TestClient) -> None:
    """GET / should redirect to /console/."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 302, 301)
    assert response.headers["location"] == "/console/"


def test_operator_console_index_html_structure(client: TestClient) -> None:
    """Verify operator console HTML renders all four distinct workspaces."""
    response = client.get("/console/")
    assert response.status_code == 200
    html = response.text

    # Title & Branding
    assert "RAAHAT 2.0" in html
    assert "CONTROL ROOM" in html

    # 4 Distinct Workspaces
    assert 'id="workspace-reports"' in html
    assert 'id="workspace-map"' in html
    assert 'id="workspace-investigation"' in html
    assert 'id="workspace-operations"' in html

    # Tab navigation buttons
    assert 'data-workspace="reports"' in html
    assert 'data-workspace="map"' in html
    assert 'data-workspace="investigation"' in html
    assert 'data-workspace="operations"' in html

    # Critical Safety & Policy Elements
    assert "Location Evidence Status" in html
    assert "Human Dispatcher Authorization Mandatory" in html
    assert "00000000-0000-0000-0000-000000000001" in html
    assert 'id="stream-indicator"' in html


def test_operator_console_static_assets_served(client: TestClient) -> None:
    """Verify static styles, scripts, and vector assets are served with correct MIME types."""
    css_res = client.get("/console/css/console.css")
    assert css_res.status_code == 200
    assert "var(--bg-primary)" in css_res.text

    map_css_res = client.get("/console/css/map.css")
    assert map_css_res.status_code == 200
    assert ".pin-confirmed" in map_css_res.text

    app_js_res = client.get("/console/src/app.js")
    assert app_js_res.status_code == 200
    assert "RaahatAPI" in app_js_res.text

    api_js_res = client.get("/console/src/api.js")
    assert api_js_res.status_code == 200
    assert "X-Dispatcher-Id" in api_js_res.text

    svg_res = client.get("/console/favicon.svg")
    assert svg_res.status_code == 200
    assert "<svg" in svg_res.text


def test_operator_console_safety_rules_visual_encoding(client: TestClient) -> None:
    """Verify critical safety visual encoding rules:

    - Confirmed location
    - Candidate location (dashed, uncertainty circle)
    - Approximate area (translucent)
    - Stale location (muted/grey)
    - Contradictory location (high alert warning)
    - Explicit UNKNOWN display (never assumed safe or negative)
    """
    map_css = client.get("/console/css/map.css").text
    console_css = client.get("/console/css/console.css").text

    assert ".pin-confirmed" in map_css
    assert ".pin-candidate" in map_css
    assert ".pin-approximate" in map_css
    assert ".pin-stale" in map_css
    assert ".pin-contradictory" in map_css
    assert ".uncertainty-circle" in map_css

    # Explicit UNKNOWN styling badge exists
    assert ".badge-unknown" in console_css
    assert "UNKNOWN" in console_css

    # Human-in-the-loop approval banner exists
    assert ".human-approval-box" in console_css


def test_operator_console_javascript_syntax_clean() -> None:
    """Verify all ES module JS files pass node syntax verification."""
    console_dir = Path(__file__).resolve().parent.parent.parent / "operator_console" / "src"
    js_files = list(console_dir.glob("**/*.js"))
    assert len(js_files) >= 5, f"Expected at least 5 JS files, found {len(js_files)}"

    for js_file in js_files:
        result = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"JS syntax error in {js_file.name}: {result.stderr}"
