"""One-shot baseline-vs-window drift testing.

Procedure (diff / check population comparisons):
1. Per-metric two-sample Mann-Whitney U test (non-parametric; scipy.stats).
2. Benjamini-Hochberg false discovery rate correction across simultaneous tests
   (Benjamini & Hochberg, 1995).
3. Omnibus decision via the Cauchy Combination Test (CCT; Liu & Xie, 2020),
   which remains valid under arbitrary unknown dependency between metrics.
   Per-metric raw p-values and effect sizes are reported alongside the global
   CCT p-value for interpretability.

Streaming live traffic uses KSWIN/MDDM instead (see streaming.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import stats

from cogscope.calibration.profiles import LENGTH_METRICS, QUALITY_METRICS
from cogscope.core.models import BehavioralFingerprint

# Core fingerprint metrics compared in batch mode
BATCH_METRICS: tuple[str, ...] = (
    "depth",
    "total_steps",
    "verification_steps",
    "hedging_ratio",
    "correction_count",
    "branching_factor",
    "uncertainty_markers",
    "tool_call_count",
)


@dataclass
class MetricTestResult:
    """Per-metric Mann-Whitney result."""

    metric: str
    p_value: float
    bh_adjusted_p: float
    bh_rejected: bool
    is_quality: bool
    is_length: bool
    baseline_mean: float
    current_mean: float
    effect_size: float = 0.0


@dataclass
class BatchDriftResult:
    """Outcome of BH + CCT batch structural drift test."""

    should_alert: bool
    cct_p_value: float
    cct_statistic: float
    alpha: float
    metric_results: list[MetricTestResult] = field(default_factory=list)
    rejected_metrics: list[str] = field(default_factory=list)
    summary: str = ""

    # Backward-compatible aliases for internal callers during transition
    @property
    def fisher_p_value(self) -> float:
        return self.cct_p_value

    @property
    def fisher_statistic(self) -> float:
        return self.cct_statistic


def _metric_values(fingerprints: list[BehavioralFingerprint], metric: str) -> list[float]:
    return [float(getattr(fp, metric)) for fp in fingerprints]


def benjamini_hochberg(
    p_values: dict[str, float],
    alpha: float = 0.05,
) -> dict[str, tuple[float, bool]]:
    """Benjamini-Hochberg FDR correction.

    Returns mapping metric -> (adjusted_p, rejected_at_alpha).
    """
    if not p_values:
        return {}

    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, tuple[float, bool]] = {}
    prev_adj = 1.0
    for rank in range(m, 0, -1):
        metric, p = items[rank - 1]
        adj = min(prev_adj, p * m / rank)
        prev_adj = adj
        adjusted[metric] = (adj, adj <= alpha)
    return adjusted


def cohens_d(baseline_vals: list[float], current_vals: list[float]) -> float:
    """Cohen's d effect size between two samples."""
    if len(baseline_vals) < 2 or len(current_vals) < 2:
        return 0.0
    b = np.asarray(baseline_vals, dtype=float)
    c = np.asarray(current_vals, dtype=float)
    n1, n2 = len(b), len(c)
    var1, var2 = np.var(b, ddof=1), np.var(c, ddof=1)
    pooled = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / max(n1 + n2 - 2, 1))
    if pooled == 0:
        return 0.0
    return float((np.mean(c) - np.mean(b)) / pooled)


def cct_combine(p_values: list[float]) -> tuple[float, float]:
    """Cauchy Combination Test (Liu & Xie, 2020).

    Combines p-values under arbitrary unknown dependency. The test statistic is
    T = (1/K) * sum(tan((0.5 - p_i) * pi)). Under the global null, T follows a
    standard Cauchy distribution.

    Returns (statistic, combined_p_value).
    """
    if not p_values:
        return 0.0, 1.0
    clipped = [max(min(p, 1.0 - 1e-16), 1e-16) for p in p_values]
    statistic = float(np.mean([np.tan((0.5 - p) * np.pi) for p in clipped]))
    # Two-sided tail against standard Cauchy null
    combined_p = float(2.0 * stats.cauchy.sf(abs(statistic)))
    return statistic, min(max(combined_p, 0.0), 1.0)


def top_metric_contributors(
    metric_results: list[MetricTestResult],
    *,
    rejected_only: bool = True,
    limit: int = 3,
) -> list[MetricTestResult]:
    """Return metrics sorted by smallest p-value for human-readable summaries."""
    pool = [m for m in metric_results if (not rejected_only or m.bh_rejected)]
    return sorted(pool, key=lambda m: m.p_value)[:limit]


def format_structural_drift_summary(result: BatchDriftResult) -> str:
    """Human-readable structural drift summary with per-metric contributors."""
    if not result.rejected_metrics:
        return "No metrics rejected after Benjamini-Hochberg correction."

    contributors = top_metric_contributors(result.metric_results)
    contrib_text = ", ".join(f"{m.metric} (p={m.p_value:.3f})" for m in contributors)
    if result.should_alert:
        return (
            f"Structural drift detected (global p={result.cct_p_value:.3f}); "
            f"largest contributors: {contrib_text}"
        )
    return (
        f"BH rejected {len(result.rejected_metrics)} metric(s) but global CCT "
        f"p={result.cct_p_value:.3f} or length guard prevented alert. "
        f"Contributors: {contrib_text}"
    )


def batch_drift_test(
    baseline_fps: list[BehavioralFingerprint],
    current_fps: list[BehavioralFingerprint],
    alpha: float = 0.05,
    metrics: tuple[str, ...] = BATCH_METRICS,
    require_quality_metric: bool = True,
) -> BatchDriftResult:
    """Run Mann-Whitney + BH + CCT on two fingerprint populations."""
    if len(baseline_fps) < 3 or len(current_fps) < 3:
        return BatchDriftResult(
            should_alert=False,
            cct_p_value=1.0,
            cct_statistic=0.0,
            alpha=alpha,
            summary="Insufficient samples for batch drift test (need >=3 per side).",
        )

    raw_p: dict[str, float] = {}
    means: dict[str, tuple[float, float]] = {}
    effect_sizes: dict[str, float] = {}

    for metric in metrics:
        b_vals = _metric_values(baseline_fps, metric)
        c_vals = _metric_values(current_fps, metric)
        b_mean = float(np.mean(b_vals))
        c_mean = float(np.mean(c_vals))
        means[metric] = (b_mean, c_mean)
        effect_sizes[metric] = cohens_d(b_vals, c_vals)
        try:
            _, p = stats.mannwhitneyu(b_vals, c_vals, alternative="two-sided")
            raw_p[metric] = float(p)
        except Exception:
            raw_p[metric] = 1.0

    bh = benjamini_hochberg(raw_p, alpha=alpha)
    metric_results: list[MetricTestResult] = []
    rejected_raw_ps: list[float] = []
    rejected_names: list[str] = []

    for metric in metrics:
        adj_p, rejected = bh.get(metric, (1.0, False))
        b_mean, c_mean = means[metric]
        metric_results.append(
            MetricTestResult(
                metric=metric,
                p_value=raw_p[metric],
                bh_adjusted_p=adj_p,
                bh_rejected=rejected,
                is_quality=metric in QUALITY_METRICS,
                is_length=metric in LENGTH_METRICS,
                baseline_mean=b_mean,
                current_mean=c_mean,
                effect_size=effect_sizes[metric],
            )
        )
        if rejected:
            rejected_names.append(metric)
            rejected_raw_ps.append(raw_p[metric])

    cct_stat, cct_p = cct_combine(rejected_raw_ps)

    quality_rejected = [m for m in rejected_names if m in QUALITY_METRICS]
    length_only = rejected_names and all(m in LENGTH_METRICS for m in rejected_names)

    should_alert = (
        len(rejected_names) >= 1
        and cct_p < alpha
        and not length_only
        and (not require_quality_metric or len(quality_rejected) >= 1)
    )

    result = BatchDriftResult(
        should_alert=should_alert,
        cct_p_value=cct_p,
        cct_statistic=cct_stat,
        alpha=alpha,
        metric_results=metric_results,
        rejected_metrics=rejected_names,
    )
    result.summary = format_structural_drift_summary(result)
    return result


def outliers_from_batch(result: BatchDriftResult) -> list[dict]:
    """Format BH-rejected metrics for TUI / event payloads."""
    outliers: list[dict] = []
    for m in result.metric_results:
        if not m.bh_rejected:
            continue
        direction = "increased" if m.current_mean > m.baseline_mean else "decreased"
        outliers.append(
            {
                "metric": m.metric,
                "p_value": m.p_value,
                "bh_adjusted_p": m.bh_adjusted_p,
                "effect_size": m.effect_size,
                "baseline_mean": m.baseline_mean,
                "current_value": m.current_mean,
                "direction": direction,
                "is_quality": m.is_quality,
                "is_length": m.is_length,
                "drift_type": "structural",
            }
        )
    return outliers
