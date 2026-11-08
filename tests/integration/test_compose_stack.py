"""Integration tests for Docker Compose infrastructure, Dockerfile, Nginx proxy, and service definitions."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def compose_config(repo_root: Path) -> dict:
    compose_file = repo_root / "compose.yaml"
    assert compose_file.exists(), "compose.yaml does not exist in project root"
    content = compose_file.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "compose.yaml did not parse as a dictionary"
    return data


def test_docker_compose_config_validates_cleanly(repo_root: Path) -> None:
    """Run `docker compose config` to verify syntax, environment substitution, and schema."""
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"docker compose config failed: {result.stderr}"


def test_compose_services_defined(compose_config: dict) -> None:
    """Verify all 6 production services are defined."""
    services = compose_config.get("services", {})
    required_services = {"db", "api", "worker", "proxy", "prometheus", "grafana"}
    assert required_services.issubset(set(services.keys()))


def test_security_database_port_not_exposed(compose_config: dict) -> None:
    """CRITICAL SECURITY RULE: PostGIS database port (5432) must NOT be exposed to host."""
    db_service = compose_config["services"]["db"]
    ports = db_service.get("ports", [])
    assert len(ports) == 0, (
        f"Database port must not be exposed in production compose file! Found: {ports}"
    )


def test_compose_healthchecks_configured(compose_config: dict) -> None:
    """All core services must declare explicit health checks."""
    services = compose_config["services"]
    for svc_name in ("db", "api", "worker", "proxy", "prometheus", "grafana"):
        svc = services[svc_name]
        assert "healthcheck" in svc, f"Service '{svc_name}' is missing a healthcheck definition!"
        assert "test" in svc["healthcheck"], f"Service '{svc_name}' healthcheck missing test command!"


def test_compose_persistent_volumes_configured(compose_config: dict) -> None:
    """Persistent volumes must be declared for database and monitoring time-series data."""
    volumes = compose_config.get("volumes", {})
    required_volumes = {"postgres_data", "prometheus_data", "grafana_data"}
    assert required_volumes.issubset(set(volumes.keys()))


def test_compose_service_dependencies(compose_config: dict) -> None:
    """Verify health-gated startup dependency ordering."""
    services = compose_config["services"]

    # API depends on healthy DB
    api_deps = services["api"].get("depends_on", {})
    assert "db" in api_deps
    assert api_deps["db"]["condition"] == "service_healthy"

    # Worker depends on healthy DB and API
    worker_deps = services["worker"].get("depends_on", {})
    assert "db" in worker_deps
    assert worker_deps["db"]["condition"] == "service_healthy"
    assert "api" in worker_deps
    assert worker_deps["api"]["condition"] == "service_healthy"

    # Nginx Proxy depends on healthy API
    proxy_deps = services["proxy"].get("depends_on", {})
    assert "api" in proxy_deps
    assert proxy_deps["api"]["condition"] == "service_healthy"

    # Grafana depends on healthy Prometheus
    grafana_deps = services["grafana"].get("depends_on", {})
    assert "prometheus" in grafana_deps
    assert grafana_deps["prometheus"]["condition"] == "service_healthy"


def test_dockerfile_security_and_non_root(repo_root: Path) -> None:
    """Verify multi-stage build and non-root execution in Dockerfile."""
    dockerfile = repo_root / "Dockerfile"
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")

    # Multi-stage check
    assert "AS builder" in content
    assert "AS runner" in content

    # Security: Dedicated user creation and USER directive
    assert "useradd" in content
    assert "USER raahat" in content

    # Health check and port exposure
    assert "HEALTHCHECK" in content
    assert "EXPOSE 8000" in content


def test_nginx_sse_buffering_disabled(repo_root: Path) -> None:
    """Verify Nginx reverse proxy configuration disables buffering for Server-Sent Events."""
    nginx_conf = repo_root / "deployment" / "nginx" / "nginx.conf"
    assert nginx_conf.exists()
    content = nginx_conf.read_text(encoding="utf-8")

    assert "location /api/v1/events/stream" in content
    assert "proxy_buffering off;" in content
    assert "chunked_transfer_encoding off;" in content
    assert "proxy_pass http://api_backend" in content


def test_env_example_documentation(repo_root: Path) -> None:
    """Verify .env.example contains documented placeholders for all key variables."""
    env_file = repo_root / ".env.example"
    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")

    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "PORT_HTTP", "GRAFANA_ADMIN_PASSWORD"):
        assert f"{var}=" in content


def test_worker_entrypoint_imports_cleanly() -> None:
    """Verify background worker entrypoint module imports without missing dependency errors."""
    import importlib

    module = importlib.import_module("raahat.workers.main")
    assert hasattr(module, "WorkerService")
