"""Prometheus-compatible metrics for cngx.

Lightweight, dependency-free metrics collection that exposes a /metrics
endpoint in Prometheus exposition format. No external dependency required.

Collected metrics:
- cngx_enforcements_total (counter): Total policy checks by result
- cngx_enforcement_latency_seconds (histogram): Policy check latency
- cngx_violations_total (counter): Violations by severity and constraint
- cngx_api_requests_total (counter): Local server/proxy request counts
"""

import threading
from collections import defaultdict
from typing import Optional


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
        self.inc(-amount, **label_values)

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
    """Thread-safe histogram with fixed buckets."""

    def __init__(
        self,
        name: str,
        description: str,
        labels: list[str],
        buckets: tuple[float, ...] = (
            0.005,
            0.01,
            0.025,
            0.05,
            0.1,
            0.25,
            0.5,
            1.0,
            2.5,
            5.0,
            10.0,
        ),
    ):
        self.name = name
        self.description = description
        self.labels = labels
        self.buckets = buckets
        self._counts: dict[tuple, list[int]] = defaultdict(lambda: [0] * len(buckets))
        self._sums: dict[tuple, float] = defaultdict(float)
        self._totals: dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **label_values: str) -> None:
        key = tuple(label_values.get(l, "") for l in self.labels)
        with self._lock:
            self._sums[key] += value
            self._totals[key] += 1
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._counts[key][i] += 1

    def collect(self) -> list[str]:
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram",
        ]
        with self._lock:
            for key in sorted(self._sums.keys()):
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key) if v)
                cumulative = 0
                for i, bound in enumerate(self.buckets):
                    cumulative += self._counts[key][i]
                    bucket_labels = f'{label_str},le="{bound}"' if label_str else f'le="{bound}"'
                    lines.append(f"{self.name}_bucket{{{bucket_labels}}} {cumulative}")
                inf_labels = f'{label_str},le="+Inf"' if label_str else 'le="+Inf"'
                lines.append(f"{self.name}_bucket{{{inf_labels}}} {self._totals[key]}")
                sum_label = f"{self.name}_sum{{{label_str}}}" if label_str else f"{self.name}_sum"
                count_label = (
                    f"{self.name}_count{{{label_str}}}" if label_str else f"{self.name}_count"
                )
                lines.append(f"{sum_label} {self._sums[key]}")
                lines.append(f"{count_label} {self._totals[key]}")
        return lines


class MetricsCollector:
    """Central metrics collector for local cngx runs."""

    def __init__(self):
        self.enforcements_total = Counter(
            "cngx_enforcements_total",
            "Total policy checks",
            ["result", "contract", "model"],
        )
        self.enforcement_latency = Histogram(
            "cngx_enforcement_latency_seconds",
            "Policy check latency in seconds",
            ["contract"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        )
        self.violations_total = Counter(
            "cngx_violations_total",
            "Total policy violations",
            ["severity", "constraint"],
        )
        self.api_requests_total = Counter(
            "cngx_api_requests_total",
            "Total local API/proxy requests",
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
        """Record a policy enforcement event."""
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
