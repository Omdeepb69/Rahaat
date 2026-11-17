"""Static checks on the deployment definition. These guard the security and
resource properties the deployment documents rely on."""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def compose() -> str:
    return (ROOT / "compose.yaml").read_text()


def _service_block(compose: str, name: str) -> str:
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|^volumes:|\Z)", compose, re.S | re.M)
    assert match, f"service {name} not found"
    return match.group(1)


def test_only_expected_services(compose: str) -> None:
    services = re.findall(r"^  (\w[\w-]*):\n", compose.split("\nservices:\n", 1)[1].split("\nvolumes:\n")[0], re.M)
    assert services == ["db", "api", "worker"]


def test_database_port_is_not_published(compose: str) -> None:
    assert "ports:" not in _service_block(compose, "db")


def test_api_is_published_on_loopback_only(compose: str) -> None:
    ports = re.findall(r'-\s*"([^"]+)"', _service_block(compose, "api"))
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)


def test_every_service_has_a_memory_limit(compose: str) -> None:
    for name in ("db", "api", "worker"):
        assert "mem_limit:" in _service_block(compose, name)


def test_required_secrets_fail_fast(compose: str) -> None:
    assert "${POSTGRES_PASSWORD:?" in compose


def test_server_entry_point_bounds_shutdown() -> None:
    source = (ROOT / "src/raahat/serve.py").read_text()
    assert "timeout_graceful_shutdown=" in source
    assert "workers=1" in source


def test_container_entrypoint_runs_migrations_before_serving() -> None:
    script = (ROOT / "scripts/container-entrypoint.sh").read_text()
    assert script.index("alembic upgrade head") < script.index("python -m raahat.serve")


def test_worker_entrypoint_imports_cleanly() -> None:
    module = importlib.import_module("raahat.workers.main")
    assert hasattr(module, "Worker") and hasattr(module, "main")


def test_env_example_documents_every_setting_the_app_reads() -> None:
    example = (ROOT / ".env.example").read_text()
    config = (ROOT / "src/raahat/config.py").read_text()
    names = set(re.findall(r'"([A-Z][A-Z0-9_]{2,})"', config)) - {"ENVIRONMENT"}
    documented = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", example, re.M))
    internal = {"DATABASE_URL", "AUDIO_STORAGE_DIR", "MAX_REQUEST_BYTES", "MAX_AUDIO_UPLOAD_BYTES",
                "API_RATE_PER_MINUTE", "PUBLIC_RATE_PER_MINUTE", "PRISMA_ENDPOINT", "TIMBRE_ENDPOINT",
                "GNANI_API_KEY", "GEOCODER_COUNTRY_CODES", "WORKER_STALE_AFTER_SECONDS",
                "PROVIDER_TIMEOUT_SECONDS"}
    missing = names - documented - internal
    assert not missing, f"settings read by config.py but absent from .env.example: {sorted(missing)}"
    assert "ENVIRONMENT=production" in example


def test_env_example_contains_no_secrets() -> None:
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.startswith(("POSTGRES_PASSWORD=", "RAAHAT_SECRET_KEY=", "GEMINI_API_KEY=", "GNANI_API_KEY_TTS_STT=", "EVON_API_KEY=")):
            assert line.endswith("="), f"example value present: {line.split('=')[0]}"
