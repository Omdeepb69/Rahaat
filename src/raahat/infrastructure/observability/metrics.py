"""Prometheus metrics instrumentation and exposition for Raahat 2.0 (RAAHAT_SPEC §11)."""
from __future__ import annotations

import threading
from typing import Optional


class Counter:
    """Thread-safe Prometheus counter metric."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, **labels: str) -> None:
        if value < 0:
            raise ValueError("Counters can only be incremented by non-negative values")
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    def get(self, **labels: str) -> float:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            for key, val in sorted(self._values.items()):
                if self.label_names:
                    lbls = ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key))
                    lines.append(f"{self.name}{{{lbls}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class Gauge:
    """Thread-safe Prometheus gauge metric."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._values: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._values[key] = float(value)

    def inc(self, value: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + value

    def dec(self, value: float = 1.0, **labels: str) -> None:
        self.inc(-value, **labels)

    def get(self, **labels: str) -> float:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            if not self._values:
                lines.append(f"{self.name} 0")
            for key, val in sorted(self._values.items()):
                if self.label_names:
                    lbls = ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key))
                    lines.append(f"{self.name}{{{lbls}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return lines


class Histogram:
    """Thread-safe Prometheus histogram metric for latencies."""

    DEFAULT_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        help_text: str,
        buckets: tuple[float, ...] = DEFAULT_BUCKETS,
        label_names: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.help_text = help_text
        self.buckets = sorted(buckets)
        self.label_names = label_names
        self._bucket_counts: dict[tuple[str, ...], dict[float, int]] = {}
        self._sums: dict[tuple[str, ...], float] = {}
        self._counts: dict[tuple[str, ...], int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(lbl, "") for lbl in self.label_names)
        with self._lock:
            if key not in self._bucket_counts:
                self._bucket_counts[key] = {b: 0 for b in self.buckets}
                self._sums[key] = 0.0
                self._counts[key] = 0

            self._counts[key] += 1
            self._sums[key] += value
            for b in self.buckets:
                if value <= b:
                    self._bucket_counts[key][b] += 1

    def render(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            if not self._counts:
                lines.append(f"{self.name}_count 0")
                lines.append(f"{self.name}_sum 0.0")
                return lines

            for key in sorted(self._counts.keys()):
                lbl_prefix = ""
                if self.label_names:
                    lbl_prefix = ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key)) + ","

                cum_count = 0
                for b in self.buckets:
                    cum_count = self._bucket_counts[key][b]
                    lines.append(f'{self.name}_bucket{{{lbl_prefix}le="{b}"}} {cum_count}')

                lines.append(f'{self.name}_bucket{{{lbl_prefix}le="+Inf"}} {self._counts[key]}')
                if self.label_names:
                    lbls = "{" + ",".join(f'{k}="{v}"' for k, v in zip(self.label_names, key)) + "}"
                    lines.append(f"{self.name}_sum{lbls} {self._sums[key]}")
                    lines.append(f"{self.name}_count{lbls} {self._counts[key]}")
                else:
                    lines.append(f"{self.name}_sum {self._sums[key]}")
                    lines.append(f"{self.name}_count {self._counts[key]}")

        return lines


class MetricsRegistry:
    """Central registry of production operational metrics for Raahat."""

    def __init__(self) -> None:
        self.reports_ingested = Counter(
            "raahat_reports_ingested_total",
            "Total number of disaster reports ingested across channels",
            label_names=("channel", "status"),
        )
        self.processing_latency = Histogram(
            "raahat_report_processing_duration_seconds",
            "End-to-end report processing latency in seconds",
            label_names=("stage",),
        )
        self.outbox_queue_pending = Gauge(
            "raahat_outbox_queue_pending_jobs",
            "Number of pending or retryable outbox jobs awaiting worker lease",
        )
        self.active_incidents = Gauge(
            "raahat_active_incidents_total",
            "Number of active unverified or verified incidents in system",
            label_names=("priority", "status"),
        )
        self.device_sync_reports = Counter(
            "raahat_device_sync_reports_total",
            "Total reports synchronized from offline field devices",
            label_names=("status",),
        )
        self.device_sync_gaps = Counter(
            "raahat_device_sync_gaps_detected_total",
            "Total monotonic sequence gaps detected during offline device audits",
        )
        self.sse_active_subscribers = Gauge(
            "raahat_sse_active_subscribers",
            "Number of live connected dispatcher SSE streams",
        )
        self.callback_jobs = Counter(
            "raahat_telephony_callback_jobs_total",
            "Total telephony outbound callback jobs handled",
            label_names=("status",),
        )

    def render_prometheus(self) -> str:
        """Render all metrics in standard Prometheus text exposition format (v0.0.4)."""
        lines: list[str] = []
        for metric in (
            self.reports_ingested,
            self.processing_latency,
            self.outbox_queue_pending,
            self.active_incidents,
            self.device_sync_reports,
            self.device_sync_gaps,
            self.sse_active_subscribers,
            self.callback_jobs,
        ):
            lines.extend(metric.render())
            lines.append("")
        return "\n".join(lines).strip() + "\n"


_GLOBAL_REGISTRY: Optional[MetricsRegistry] = None
_INIT_LOCK = threading.Lock()


def get_metrics_registry() -> MetricsRegistry:
    """Return singleton application metrics registry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        with _INIT_LOCK:
            if _GLOBAL_REGISTRY is None:
                _GLOBAL_REGISTRY = MetricsRegistry()
    return _GLOBAL_REGISTRY
