"""Unit tests for Prometheus metrics collection and /metrics HTTP endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from raahat.api.app import create_app
from raahat.infrastructure.observability import (
    Histogram,
    MetricsRegistry,
)


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_metrics_registry_counter_and_gauge() -> None:
    reg = MetricsRegistry()

    # Counter
    reg.reports_ingested.inc(1, channel="ivr", status="success")
    reg.reports_ingested.inc(2, channel="ivr", status="success")
    reg.reports_ingested.inc(1, channel="web", status="success")

    assert reg.reports_ingested.get(channel="ivr", status="success") == 3.0
    assert reg.reports_ingested.get(channel="web", status="success") == 1.0

    # Gauge
    reg.outbox_queue_pending.set(15)
    assert reg.outbox_queue_pending.get() == 15.0

    reg.outbox_queue_pending.inc(5)
    assert reg.outbox_queue_pending.get() == 20.0

    reg.outbox_queue_pending.dec(8)
    assert reg.outbox_queue_pending.get() == 12.0


def test_metrics_registry_histogram() -> None:
    hist = Histogram("test_duration_seconds", "Test duration", buckets=(0.1, 0.5, 1.0))
    hist.observe(0.05)
    hist.observe(0.2)
    hist.observe(0.8)

    rendered = "\n".join(hist.render())
    assert "test_duration_seconds_bucket" in rendered
    assert "test_duration_seconds_count 3" in rendered


def test_metrics_endpoint_exposition_format(client: TestClient) -> None:
    """Verify both /metrics and /api/v1/metrics return valid Prometheus text exposition format."""
    for path in ("/metrics", "/api/v1/metrics"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        text = response.text
        # Verify Prometheus comment directives
        assert "# HELP raahat_reports_ingested_total" in text
        assert "# TYPE raahat_reports_ingested_total counter" in text
        assert "# HELP raahat_outbox_queue_pending_jobs" in text
        assert "# TYPE raahat_outbox_queue_pending_jobs gauge" in text
        assert "# HELP raahat_active_incidents_total" in text
        assert "# HELP raahat_sse_active_subscribers" in text
