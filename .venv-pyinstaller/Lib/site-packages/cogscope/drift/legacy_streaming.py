"""Legacy ADWIN/Page-Hinkley streaming detectors (pre KSWIN/MDDM upgrade).

Retained only for benchmark comparisons measuring false-positive rate
improvement on noisy non-stationary streams.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frouros.detectors.concept_drift.streaming import ADWIN, ADWINConfig

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


class PageHinkleyTwoSided:
    """Classic Page (1954) two-sided CUSUM for mean shifts up or down."""

    def __init__(self, delta: float = 0.005, lambda_: float = 8.0) -> None:
        self.delta = delta
        self.lambda_ = lambda_
        self.n = 0
        self.mean = 0.0
        self.ph_up_sum = 0.0
        self.ph_up_min = 0.0
        self.ph_down_sum = 0.0
        self.ph_down_max = 0.0

    def update(self, x: float) -> bool:
        self.n += 1
        self.mean += (x - self.mean) / self.n
        self.ph_up_sum += x - self.mean - self.delta
        self.ph_up_min = min(self.ph_up_min, self.ph_up_sum)
        up = (self.ph_up_sum - self.ph_up_min) > self.lambda_
        self.ph_down_sum += self.mean - x - self.delta
        self.ph_down_max = max(self.ph_down_max, self.ph_down_sum)
        down = (self.ph_down_sum - self.ph_down_max) > self.lambda_
        return up or down


@dataclass
class LegacyStreamingMetricState:
    adwin: ADWIN = field(
        default_factory=lambda: ADWIN(config=ADWINConfig(min_num_instances=8, delta=0.002))
    )
    page_hinkley: PageHinkleyTwoSided = field(default_factory=PageHinkleyTwoSided)
    last_drift: bool = False

    def seed(self, values: list[float]) -> None:
        for v in values:
            self._update_internal(float(v), track_drift=False)

    def update(self, value: float) -> bool:
        return self._update_internal(float(value), track_drift=True)

    def _update_internal(self, value: float, track_drift: bool) -> bool:
        self.adwin.update(value=value)
        ph_drift = self.page_hinkley.update(value)
        drift = bool(self.adwin.drift or ph_drift)
        if track_drift:
            self.last_drift = drift
        return drift if track_drift else False


@dataclass
class LegacyStreamingDriftMonitor:
    min_drift_metrics: int = 2
    require_quality_metric: bool = True
    _metrics: dict[str, LegacyStreamingMetricState] = field(default_factory=dict)
    _seeded: bool = False

    def __post_init__(self) -> None:
        if not self._metrics:
            self._metrics = {m: LegacyStreamingMetricState() for m in STREAMING_METRICS}

    def seed_from_history(self, fingerprints: list[BehavioralFingerprint]) -> None:
        for metric in STREAMING_METRICS:
            values = [float(getattr(fp, metric)) for fp in fingerprints]
            if values:
                self._metrics[metric].seed(values)
        self._seeded = True

    def update(self, fingerprint: BehavioralFingerprint) -> dict[str, bool]:
        flags: dict[str, bool] = {}
        for metric in STREAMING_METRICS:
            value = float(getattr(fingerprint, metric))
            flags[metric] = self._metrics[metric].update(value)
        return flags

    def combine_streaming_signals(
        self,
        drift_flags: dict[str, bool],
    ) -> tuple[bool, list[dict]]:
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
            }
            for m in drifted
        ]
        return should_alert, details
