"""Prometheus-compatible metrics for Cogscope.

Lightweight, dependency-free metrics collection that exposes a /metrics
endpoint in Prometheus exposition format. No external dependency required.

Collected metrics:
- rvc_enforcements_total (counter): Total enforcement checks by result
- rvc_enforcement_latency_seconds (histogram): Enforcement check latency
- rvc_active_organizations (gauge): Currently active organizations
- rvc_contracts_total (gauge): Total contracts in registry
- rvc_violations_total (counter): Violations by severity and constraint
- rvc_webhook_deliveries_total (counter): Webhook delivery attempts
"""

import threading
import time
from collections import defaultdict
from typing import Any, Optional


class Counter:
    """Thread-safe counter metric."""

    def __init__(self, name: str, description: str, labels: list[str]):
        self.name = name
        self.description = description
        self.labels = labels
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] += amount

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter",
        ]
        with self._lock:
            for key, value in sorted(self._values.items()):
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key) if v)
                if label_str:
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return lines


class Gauge:
    """Thread-safe gauge metric."""

    def __init__(self, name: str, description: str, labels: list[str]):
        self.name = name
        self.description = description
        self.labels = labels
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] += amount

    def dec(self, amount: float = 1.0, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._values[key] -= amount

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge",
        ]
        with self._lock:
            for key, value in sorted(self._values.items()):
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key) if v)
                if label_str:
                    lines.append(f"{self.name}{{{label_str}}} {value}")
                else:
                    lines.append(f"{self.name} {value}")
        return lines


class Histogram:
    """Thread-safe histogram metric with configurable buckets."""

    DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(
        self,
        name: str,
        description: str,
        labels: list[str],
        buckets: Optional[tuple[float, ...]] = None,
    ):
        self.name = name
        self.description = description
        self.labels = labels
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: dict[tuple, dict[float, int]] = defaultdict(
            lambda: {b: 0 for b in self.buckets}
        )
        self._sums: dict[tuple, float] = defaultdict(float)
        self._totals: dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._sums[key] += value
            self._totals[key] += 1
            for bucket in self.buckets:
                if value <= bucket:
                    self._counts[key][bucket] += 1

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            for key in sorted(set(list(self._counts.keys()) + list(self._sums.keys()))):
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key) if v)
                base = f"{self.name}{{{label_str}," if label_str else f"{self.name}{{"

                cumulative = 0
                for bucket in self.buckets:
                    cumulative += self._counts[key].get(bucket, 0)
                    lines.append(f'{base}le="{bucket}"}} {cumulative}')
                lines.append(f'{base}le="+Inf"}} {self._totals[key]}')
                sum_label = f"{self.name}_sum{{{label_str}}}" if label_str else f"{self.name}_sum"
                count_label = (
                    f"{self.name}_count{{{label_str}}}" if label_str else f"{self.name}_count"
                )
                lines.append(f"{sum_label} {self._sums[key]}")
                lines.append(f"{count_label} {self._totals[key]}")
        return lines


# ---------------------------------------------------------------------------
# Cogscope Metrics Collector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Central metrics collector for Cogscope Cloud."""

    def __init__(self):
        self.enforcements_total = Counter(
            "rvc_enforcements_total",
            "Total enforcement checks",
            ["result", "contract", "model"],
        )
        self.enforcement_latency = Histogram(
            "rvc_enforcement_latency_seconds",
            "Enforcement check latency in seconds",
            ["contract"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
        self.violations_total = Counter(
            "rvc_violations_total",
            "Total contract violations",
            ["severity", "constraint"],
        )
        self.active_orgs = Gauge(
            "rvc_active_organizations",
            "Currently active organizations",
            [],
        )
        self.contracts_total = Gauge(
            "rvc_contracts_total",
            "Total contracts in registry",
            ["org_id"],
        )
        self.webhook_deliveries = Counter(
            "rvc_webhook_deliveries_total",
            "Webhook delivery attempts",
            ["status", "event"],
        )
        self.api_requests_total = Counter(
            "rvc_api_requests_total",
            "Total API requests",
            ["method", "endpoint", "status"],
        )

    def record_enforcement(
        self,
        result: str,
        contract: str,
        model: str,
        latency_seconds: float,
        violations: Optional[list[dict]] = None,
    ) -> None:
        """Record an enforcement event."""
        self.enforcements_total.inc(result=result, contract=contract, model=model)
        self.enforcement_latency.observe(latency_seconds, contract=contract)

        if violations:
            for v in violations:
                self.violations_total.inc(
                    severity=v.get("severity", "unknown"),
                    constraint=v.get("constraint", "unknown"),
                )

    def collect(self) -> str:
        """Collect all metrics in Prometheus exposition format."""
        all_lines: list[str] = []
        for metric in [
            self.enforcements_total,
            self.enforcement_latency,
            self.violations_total,
            self.active_orgs,
            self.contracts_total,
            self.webhook_deliveries,
            self.api_requests_total,
        ]:
            all_lines.extend(metric.collect())
            all_lines.append("")

        return "\n".join(all_lines)


# Global singleton
_metrics: Optional[MetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics
    if _metrics is None:
        with _metrics_lock:
            if _metrics is None:
                _metrics = MetricsCollector()
    return _metrics
