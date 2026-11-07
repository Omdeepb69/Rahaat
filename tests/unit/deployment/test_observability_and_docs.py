"""Unit tests for Grafana dashboard schemas, provisioning configs, and documentation completeness."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def test_grafana_dashboard_provisioning_yaml(repo_root: Path) -> None:
    """Verify Grafana dashboard provider YAML parses correctly and targets expected path."""
    prov_file = repo_root / "deployment" / "grafana" / "provisioning" / "dashboards" / "dashboards.yml"
    assert prov_file.exists()
    content = prov_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert isinstance(data, dict)
    assert "providers" in data
    assert len(data["providers"]) > 0
    provider = data["providers"][0]
    assert provider["name"] == "Raahat Disaster Intelligence"


def test_grafana_dashboard_json_schema(repo_root: Path) -> None:
    """Verify Grafana dashboard JSON is well-formed and includes required metric queries."""
    for dashboard_path in (
        repo_root / "deployment" / "grafana" / "dashboards" / "raahat_overview.json",
        repo_root / "deployment" / "grafana" / "provisioning" / "dashboards" / "json" / "raahat_overview.json",
    ):
        assert dashboard_path.exists(), f"Dashboard missing at {dashboard_path}"
        content = dashboard_path.read_text(encoding="utf-8")
        data = json.loads(content)

        assert data["title"] == "Raahat Disaster Intelligence & Operations Overview"
        assert data["uid"] == "raahat-overview-v1"
        assert "panels" in data
        assert len(data["panels"]) >= 6

        # Check for presence of essential metric expressions
        json_str = json.dumps(data)
        assert "raahat_reports_ingested_total" in json_str
        assert "raahat_outbox_queue_pending_jobs" in json_str
        assert "raahat_report_processing_duration_seconds" in json_str
        assert "raahat_active_incidents_total" in json_str


def test_documentation_files_present_and_comprehensive(repo_root: Path) -> None:
    """Verify presence and minimum depth of operational runbook, security, and limitations docs."""
    docs_dir = repo_root / "docs"
    assert docs_dir.exists()

    required_docs = {
        "operations_runbook.md": 2000,  # Min character length
        "security.md": 1500,
        "limitations.md": 1500,
    }

    for filename, min_len in required_docs.items():
        doc_path = docs_dir / filename
        assert doc_path.exists(), f"Required documentation file {filename} is missing!"
        content = doc_path.read_text(encoding="utf-8")
        assert len(content) >= min_len, f"{filename} is too brief ({len(content)} chars < {min_len})"
        assert content.startswith("#"), f"{filename} missing top-level markdown heading"
