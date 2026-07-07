"""Streaming concept-drift detection for live proxy traffic.

Uses KSWIN (Raab et al., 2020) on count/continuous metrics and MDDM
(Pesaranghader et al., 2018) on ratio-like metrics. KSWIN compares empirical
CDFs in a sliding window via Kolmogorov-Smirnov, which tolerates the natural
variance of generative text metrics better than mean-only cumulative-sum tests.
MDDM applies McDiarmid-type bounds on a weighted window that favors recent
samples, suited to gradual shifts in hedging ratio and similar bounded signals.

Each metric stream is independent; user-facing structural drift alerts require
corroboration across multiple metrics (see combine_streaming_signals).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from frouros.detectors.concept_drift.streaming.window_based.kswin import KSWIN, KSWINConfig

from cogscope.calibration.profiles import LENGTH_METRICS, QUALITY_METRICS
from cogscope.core.models import BehavioralFingerprint

STREAMING_METRICS: tuple[str, ...] = (
    "depth",
    "total_steps",
    "verification_steps",
    "hedging_ratio",
    "correction_count",
    "branching_factor",
    "uncertainty_markers",
)

# KSWIN for count/continuous metrics; MDDM for ratio-like metrics
KSWIN_METRICS: frozenset[str] = frozenset(
    {
        "depth",
        "total_steps",
        "verification_steps",
        "correction_count",
        "branching_factor",
        "uncertainty_markers",
    }
)
MDDM_METRICS: frozenset[str] = frozenset({"hedging_ratio"})


class MDDMDetector:
    """MDDM-style weighted sliding window detector (Pesaranghader et al., 2018).

    Uses linearly increasing weights toward recent observations and a McDiarmid-type
    control limit on weighted-mean shift vs the older half of the reference window.
    """

    def __init__(
        self,
        window_size: int = 40,
        alpha: float = 0.001,
    ) -> None:
        self.window_size = window_size
        self.alpha = alpha
        self.values: deque[float] = deque(maxlen=window_size)
        self.last_drift = False

    def seed(self, values: list[float]) -> None:
        for v in values:
            self._update_internal(float(v), track_drift=False)

    def update(self, value: float) -> bool:
        return self._update_internal(float(value), track_drift=True)

    def _update_internal(self, value: float, track_drift: bool) -> bool:
        self.values.append(value)
        if len(self.values) < self.window_size:
            if track_drift:
                self.last_drift = False
            return False

        arr = np.asarray(self.values, dtype=float)
        n = len(arr)
        weights = np.linspace(1.0, 2.0, n)
        weights /= weights.sum()
        weighted_mean = float(np.average(arr, weights=weights))

        half = max(2, n // 2)
        ref = arr[:half]
        ref_mean = float(np.mean(ref))
        value_range = float(np.max(arr) - np.min(arr)) + 1e-9
        epsilon = value_range * float(np.sqrt(-np.log(self.alpha / 2.0) / (2.0 * half)))

        drift = abs(weighted_mean - ref_mean) > epsilon
        if track_drift:
            self.last_drift = drift
        return drift if track_drift else False


@dataclass
class StreamingMetricState:
    """KSWIN or MDDM detector for one metric stream."""

    metric: str
    kswin: Optional[KSWIN] = None
    mddm: Optional[MDDMDetector] = None
    last_drift: bool = False
    updates: int = 0

    def __post_init__(self) -> None:
        if self.metric in KSWIN_METRICS and self.kswin is None:
            self.kswin = KSWIN(
                config=KSWINConfig(alpha=0.05, min_num_instances=30, num_test_instances=15)
            )
        if self.metric in MDDM_METRICS and self.mddm is None:
            self.mddm = MDDMDetector()

    def seed(self, values: list[float]) -> None:
        for v in values:
            self._update_internal(float(v), track_drift=False)

    def update(self, value: float) -> bool:
        return self._update_internal(float(value), track_drift=True)

    def _update_internal(self, value: float, track_drift: bool) -> bool:
        drift = False
        if self.kswin is not None:
            self.kswin.update(value=value)
            drift = bool(self.kswin.drift)
        elif self.mddm is not None:
            drift = self.mddm.update(value)
        self.updates += 1
        if track_drift:
            self.last_drift = drift
        return drift if track_drift else False


@dataclass
class StreamingKey:
    model: str
    baseline_name: str

    def as_tuple(self) -> tuple[str, str]:
        return (self.model, self.baseline_name)


class StreamingDriftMonitor:
    """One monitor per (model, pinned baseline) with per-metric detectors."""

    def __init__(
        self,
        min_drift_metrics: int = 2,
        require_quality_metric: bool = True,
    ):
        self.min_drift_metrics = min_drift_metrics
        self.require_quality_metric = require_quality_metric
        self._metrics: dict[str, StreamingMetricState] = {
            m: StreamingMetricState(metric=m) for m in STREAMING_METRICS
        }
        self._seeded = False

    def seed_from_history(self, fingerprints: list[BehavioralFingerprint]) -> None:
        """Initialize streams from baseline-era fingerprints."""
        for metric in STREAMING_METRICS:
            values = [float(getattr(fp, metric)) for fp in fingerprints]
            if values:
                self._metrics[metric].seed(values)
        self._seeded = True

    def update(self, fingerprint: BehavioralFingerprint) -> dict[str, bool]:
        """Update all metric streams; return per-metric drift flags this step."""
        flags: dict[str, bool] = {}
        for metric in STREAMING_METRICS:
            value = float(getattr(fingerprint, metric))
            flags[metric] = self._metrics[metric].update(value)
        return flags

    def combine_streaming_signals(
        self,
        drift_flags: dict[str, bool],
    ) -> tuple[bool, list[dict]]:
        """Corroboration: >=2 metrics with KSWIN/MDDM drift, >=1 quality, not length-only."""
        drifted = [
            m for m in STREAMING_METRICS if drift_flags.get(m) or self._metrics[m].last_drift
        ]
        if len(drifted) < self.min_drift_metrics:
            return False, []

        quality_drifted = [m for m in drifted if m in QUALITY_METRICS]
        length_only = all(m in LENGTH_METRICS for m in drifted)

        should_alert = not length_only and (
            not self.require_quality_metric or len(quality_drifted) >= 1
        )

        details = [
            {
                "metric": m,
                "streaming_drift": True,
                "is_quality": m in QUALITY_METRICS,
                "is_length": m in LENGTH_METRICS,
                "direction": "shift detected",
                "drift_type": "structural",
                "detector": "kswin" if m in KSWIN_METRICS else "mddm",
            }
            for m in drifted
        ]
        return should_alert, details


class StreamingDriftRegistry:
    """Process-wide registry of streaming monitors keyed by model + baseline."""

    def __init__(self) -> None:
        self._monitors: dict[tuple[str, str], StreamingDriftMonitor] = {}
        self._lock = threading.Lock()

    def get_or_create(
        self,
        model: str,
        baseline_name: str,
    ) -> StreamingDriftMonitor:
        key = (model, baseline_name)
        with self._lock:
            if key not in self._monitors:
                self._monitors[key] = StreamingDriftMonitor()
            return self._monitors[key]

    def reset(self, model: Optional[str] = None, baseline_name: Optional[str] = None) -> None:
        with self._lock:
            if model is None and baseline_name is None:
                self._monitors.clear()
                return
            keys = [
                k
                for k in self._monitors
                if (model is None or k[0] == model)
                and (baseline_name is None or k[1] == baseline_name)
            ]
            for k in keys:
                del self._monitors[k]


_registry: Optional[StreamingDriftRegistry] = None


def get_streaming_registry() -> StreamingDriftRegistry:
    global _registry
    if _registry is None:
        _registry = StreamingDriftRegistry()
    return _registry
