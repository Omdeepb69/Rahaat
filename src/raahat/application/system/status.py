"""System and integration status.

Every status reported here is the result of a check that actually ran:

* ``operational``     the last real check or call succeeded
* ``degraded``        working, with a condition that needs attention
* ``unavailable``     the last real check or call failed
* ``not_configured``  required settings are absent in this deployment
* ``unknown``         configured, but nothing has exercised it yet

Core components (database, worker, realtime listener, host) are checked on
every request. External providers are not called on every page load; their
status is the stored result of the last real call or of a probe an
administrator ran, shown with its age.
"""
from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from raahat.application.ai.registry import Providers
from raahat.config import Settings
from raahat.infrastructure.database.models.system import (
    IntegrationCheckModel,
    WorkerHeartbeatModel,
)
from raahat.infrastructure.providers.base import ProviderError, ProviderNotConfigured

OPERATIONAL = "operational"
DEGRADED = "degraded"
UNAVAILABLE = "unavailable"
NOT_CONFIGURED = "not_configured"
UNKNOWN = "unknown"

_SEVERITY = {OPERATIONAL: 0, NOT_CONFIGURED: 0, UNKNOWN: 1, DEGRADED: 2, UNAVAILABLE: 3}
DISK_WARN_FRACTION = 0.10
MEMORY_WARN_FRACTION = 0.10
QUEUE_WARN_SECONDS = 300


@dataclass
class ComponentStatus:
    key: str
    name: str
    group: str  # core | provider | host
    status: str
    detail: str
    checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    latency_ms: Optional[float] = None
    required: bool = False
    can_probe: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expected_revision() -> Optional[str]:
    root = Path(__file__).resolve().parents[2] / "infrastructure" / "database" / "migrations"
    try:
        config = Config()
        config.set_main_option("script_location", str(root))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # packaging problem: report as unknown rather than crash the status page
        return None


EXPECTED_REVISION = _expected_revision()


def check_database(session: Session) -> ComponentStatus:
    started = time.perf_counter()
    try:
        row = session.execute(
            text(
                "SELECT (SELECT version_num FROM alembic_version LIMIT 1) AS revision, "
                "postgis_lib_version() AS postgis, "
                "pg_database_size(current_database()) AS size_bytes, "
                "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections"
            )
        ).one()
    except Exception as exc:
        session.rollback()
        return ComponentStatus(
            "database", "Database", "core", UNAVAILABLE,
            f"Query failed: {type(exc).__name__}", checked_at=_now(), required=True,
        )
    latency = round((time.perf_counter() - started) * 1000, 1)
    status, detail = OPERATIONAL, f"PostgreSQL with PostGIS {row.postgis}"
    if EXPECTED_REVISION and row.revision != EXPECTED_REVISION:
        status = DEGRADED
        detail = (
            f"Schema is at revision {row.revision}; the application expects "
            f"{EXPECTED_REVISION}. Run migrations."
        )
    return ComponentStatus(
        "database", "Database", "core", status, detail, checked_at=_now(),
        last_success_at=_now(), latency_ms=latency, required=True,
        metrics={
            "schema_revision": row.revision,
            "size_bytes": int(row.size_bytes),
            "connections": int(row.connections),
        },
    )


def check_worker(session: Session, settings: Settings) -> ComponentStatus:
    beat = session.execute(
        select(WorkerHeartbeatModel).order_by(WorkerHeartbeatModel.last_beat_at.desc()).limit(1)
    ).scalar_one_or_none()
    queue = session.execute(
        text(
            "SELECT count(*) AS waiting, "
            "EXTRACT(EPOCH FROM (now() - min(received_at))) AS oldest_seconds "
            "FROM reports WHERE processing_status IN ('pending','pending_enrichment','claimed')"
        )
    ).one()
    metrics = {
        "reports_waiting": int(queue.waiting),
        "oldest_waiting_seconds": round(float(queue.oldest_seconds), 0) if queue.oldest_seconds else None,
    }
    if beat is None:
        return ComponentStatus(
            "worker", "Background worker", "core", UNAVAILABLE,
            "No worker has ever reported in. Audio and enrichment will not be processed.",
            checked_at=_now(), required=True, metrics=metrics,
        )
    age = (_now() - beat.last_beat_at).total_seconds()
    metrics["last_heartbeat_seconds_ago"] = round(age, 1)
    metrics.update({k: v for k, v in (beat.details or {}).items() if k in ("processed_total", "failed_total")})
    if age > settings.worker_stale_after_seconds:
        return ComponentStatus(
            "worker", "Background worker", "core", UNAVAILABLE,
            f"Last heartbeat {age:.0f} s ago. The worker has stopped; "
            f"{queue.waiting} report(s) are waiting.",
            checked_at=_now(), last_success_at=beat.last_beat_at, required=True, metrics=metrics,
        )
    if queue.oldest_seconds and queue.oldest_seconds > QUEUE_WARN_SECONDS:
        return ComponentStatus(
            "worker", "Background worker", "core", DEGRADED,
            f"Running, but the oldest waiting report has been queued for "
            f"{queue.oldest_seconds / 60:.0f} min.",
            checked_at=_now(), last_success_at=beat.last_beat_at, required=True, metrics=metrics,
        )
    return ComponentStatus(
        "worker", "Background worker", "core", OPERATIONAL,
        f"Heartbeat {age:.0f} s ago; {queue.waiting} report(s) waiting.",
        checked_at=_now(), last_success_at=beat.last_beat_at, required=True, metrics=metrics,
    )


def check_realtime(hub_status: dict[str, Any]) -> ComponentStatus:
    metrics = {
        "subscribers": hub_status.get("subscribers", 0),
        "last_notification_at": hub_status.get("last_notification_at"),
    }
    if hub_status.get("listening"):
        return ComponentStatus(
            "realtime", "Realtime event stream", "core", OPERATIONAL,
            f"Listening for database notifications; {metrics['subscribers']} client(s) connected.",
            checked_at=_now(), last_success_at=_now(), required=True, metrics=metrics,
        )
    return ComponentStatus(
        "realtime", "Realtime event stream", "core", DEGRADED,
        "The notification listener is not connected "
        f"({hub_status.get('last_error') or 'starting'}). Clients fall back to a 5-second re-check.",
        checked_at=_now(), required=True, metrics=metrics,
    )


def check_host(settings: Settings) -> ComponentStatus:
    metrics: dict[str, Any] = {}
    problems: list[str] = []
    try:
        usage = shutil.disk_usage(settings.audio_storage_dir if settings.audio_storage_dir.exists() else ".")
        metrics["disk_free_bytes"] = usage.free
        metrics["disk_total_bytes"] = usage.total
        if usage.free / usage.total < DISK_WARN_FRACTION:
            problems.append(f"disk {usage.free / 1e9:.1f} GB free")
    except OSError:
        pass
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    info[key] = int(rest.split()[0]) * 1024
        metrics["memory_total_bytes"] = info.get("MemTotal")
        metrics["memory_available_bytes"] = info.get("MemAvailable")
        if info.get("MemTotal") and info.get("MemAvailable") is not None:
            if info["MemAvailable"] / info["MemTotal"] < MEMORY_WARN_FRACTION:
                problems.append(f"memory {info['MemAvailable'] / 1e9:.1f} GB available")
    except OSError:
        pass
    try:
        load1, _, _ = os.getloadavg()
        cores = os.cpu_count() or 1
        metrics["load_1m"] = round(load1, 2)
        metrics["cpu_count"] = cores
        if load1 > cores * 1.5:
            problems.append(f"load {load1:.1f} on {cores} cores")
    except OSError:
        pass
    if problems:
        return ComponentStatus(
            "host", "Host resources", "host", DEGRADED,
            "Low headroom: " + "; ".join(problems), checked_at=_now(), metrics=metrics,
        )
    return ComponentStatus(
        "host", "Host resources", "host", OPERATIONAL,
        "Disk, memory and load are within limits.", checked_at=_now(),
        last_success_at=_now(), metrics=metrics,
    )


# ----------------------------------------------------------------- providers
@dataclass(frozen=True)
class IntegrationSpec:
    key: str
    name: str
    purpose: str
    configured: Callable[[Settings, Providers], bool]
    missing: str
    probe: Optional[Callable[[Providers], float]] = None


def _probe_text_model(providers: Providers) -> float:
    assert providers.text_model is not None
    completion = providers.text_model.complete_json(
        system='Reply with the JSON object {"ok": true} and nothing else.',
        user="Health check.",
        max_tokens=64,
    )
    if completion.data.get("ok") is not True:
        raise ProviderError(completion.provider, "unexpected reply to health check")
    return completion.duration_ms


INTEGRATIONS: tuple[IntegrationSpec, ...] = (
    IntegrationSpec(
        "speech", "Speech recognition (Gnani Prisma)", "Transcribes audio reports",
        lambda s, p: p.speech.configured, "GNANI_API_KEY_TTS_STT",
    ),
    IntegrationSpec(
        "text_model", "Extraction and translation model",
        "Translates reports to English and extracts structured facts",
        lambda s, p: p.text_model is not None and p.text_model.configured,
        "LLM_PROVIDER with EVON_API_BASE or GEMINI_API_KEY",
        probe=_probe_text_model,
    ),
    IntegrationSpec(
        "geocoder", "Geocoder (Nominatim)", "Looks up place names on request",
        lambda s, p: p.geocoder.configured, "GEOCODER_PROVIDER=nominatim",
        probe=lambda p: p.geocoder.probe(),
    ),
    IntegrationSpec(
        "routing", "Road routing (OSRM)", "Road distance and travel time for recommendations",
        lambda s, p: p.routing.configured, "ROUTING_PROVIDER=osrm and OSRM_BASE_URL",
        probe=lambda p: p.routing.probe(),
    ),
    IntegrationSpec(
        "alerts", "Official alert feed (CAP)", "Imports published disaster alerts, polled every 5 minutes",
        lambda s, p: p.alerts.configured, "CAP_ALERT_FEED_URL",
    ),
)
_SPECS = {spec.key: spec for spec in INTEGRATIONS}


def record_integration_result(
    session: Session, key: str, *, ok: bool, detail: str, latency_ms: Optional[float] = None
) -> None:
    """Store the outcome of a real provider call or probe."""
    row = session.get(IntegrationCheckModel, key)
    now = _now()
    if row is None:
        row = IntegrationCheckModel(integration=key, status=UNKNOWN)
        session.add(row)
    row.status = OPERATIONAL if ok else UNAVAILABLE
    row.detail = detail[:500]
    row.latency_ms = latency_ms
    row.checked_at = now
    if ok:
        row.last_success_at = now
    else:
        row.last_error = detail[:500]
        row.last_error_at = now


def integration_statuses(
    session: Session, settings: Settings, providers: Providers
) -> list[ComponentStatus]:
    stored = {row.integration: row for row in session.execute(select(IntegrationCheckModel)).scalars()}
    out: list[ComponentStatus] = []
    for spec in INTEGRATIONS:
        if not spec.configured(settings, providers):
            out.append(
                ComponentStatus(
                    spec.key, spec.name, "provider", NOT_CONFIGURED,
                    f"{spec.purpose}. Not configured: set {spec.missing}.",
                )
            )
            continue
        row = stored.get(spec.key)
        if row is None:
            out.append(
                ComponentStatus(
                    spec.key, spec.name, "provider", UNKNOWN,
                    f"{spec.purpose}. Configured, but not yet used or checked.",
                    can_probe=spec.probe is not None,
                )
            )
            continue
        out.append(
            ComponentStatus(
                spec.key, spec.name, "provider", row.status,
                row.detail or spec.purpose, checked_at=row.checked_at,
                last_success_at=row.last_success_at, latency_ms=row.latency_ms,
                can_probe=spec.probe is not None,
                metrics={"last_error": row.last_error, "last_error_at": row.last_error_at},
            )
        )
    return out


def run_probe(session: Session, key: str, settings: Settings, providers: Providers) -> ComponentStatus:
    """Make one real request to the provider and store the result."""
    spec = _SPECS.get(key)
    if spec is None:
        raise LookupError("Unknown integration")
    if not spec.configured(settings, providers):
        raise ValueError(f"Not configured: set {spec.missing}")
    if spec.probe is None:
        raise ValueError(
            "This integration has no side-effect-free probe; its status updates when it is used"
        )
    try:
        latency = spec.probe(providers)
    except ProviderNotConfigured as exc:
        raise ValueError(str(exc)) from exc
    except ProviderError as exc:
        record_integration_result(session, key, ok=False, detail=str(exc))
    else:
        record_integration_result(
            session, key, ok=True, detail="Probe succeeded", latency_ms=latency
        )
    session.flush()
    return next(c for c in integration_statuses(session, settings, providers) if c.key == key)


def overall(components: list[ComponentStatus]) -> str:
    """Worst status among required components; optional ones cannot make the system unavailable."""
    worst = OPERATIONAL
    for component in components:
        status = component.status
        if not component.required and status == UNAVAILABLE:
            status = DEGRADED
        if not component.required and status == UNKNOWN:
            continue
        if _SEVERITY[status] > _SEVERITY[worst]:
            worst = status
    return worst
