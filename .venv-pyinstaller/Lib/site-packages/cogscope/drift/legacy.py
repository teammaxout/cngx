"""Legacy ad hoc rules retained for benchmark comparisons.

Measures false-positive rate improvement vs upgraded CCT/KSWIN/MDDM engine.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from cogscope.calibration.profiles import (
    LENGTH_METRICS,
    QUALITY_METRICS,
    get_adaptive_thresholds,
)
from cogscope.core.models import BehavioralFingerprint
from cogscope.drift.batch import (
    BATCH_METRICS,
    benjamini_hochberg,
)


def legacy_multimetric_outlier(
    current: BehavioralFingerprint,
    historical: list[BehavioralFingerprint],
    model_name: str,
    z_threshold: float = 2.0,
    min_outlier_metrics: int = 2,
) -> tuple[bool, list[dict]]:
    """Original z-score + >=2 metrics + quality guard rule."""
    thresholds = get_adaptive_thresholds(model_name)
    population = list(historical) if historical else [current]
    distribution = thresholds.build_metric_distribution(population)

    outliers: list[dict] = []
    for metric, (mean, _std) in distribution.items():
        value = float(getattr(current, metric))
        z = thresholds.metric_z_score(metric, value, distribution)
        if z >= z_threshold:
            direction = "increased" if value > mean else "decreased"
            outliers.append(
                {
                    "metric": metric,
                    "z_score": z,
                    "baseline_mean": mean,
                    "current_value": value,
                    "direction": direction,
                    "is_quality": metric in QUALITY_METRICS,
                    "is_length": metric in LENGTH_METRICS,
                }
            )

    if len(outliers) < min_outlier_metrics:
        return False, outliers

    quality_hits = [o for o in outliers if o["is_quality"]]
    length_only = all(o["is_length"] for o in outliers)
    should_alert = len(quality_hits) >= 1 and not length_only
    return should_alert, outliers


def legacy_batch_population_alert(
    baseline_fps: list[BehavioralFingerprint],
    current_fps: list[BehavioralFingerprint],
    alpha: float = 0.05,
) -> bool:
    """Old batch rule: Mann-Whitney per metric, alert if >=2 metrics with p < alpha."""
    from scipy import stats

    from cogscope.drift.batch import BATCH_METRICS

    significant = 0
    for metric in BATCH_METRICS:
        b_vals = [float(getattr(fp, metric)) for fp in baseline_fps]
        c_vals = [float(getattr(fp, metric)) for fp in current_fps]
        if len(b_vals) < 3 or len(c_vals) < 3:
            continue
        try:
            _, p = stats.mannwhitneyu(b_vals, c_vals, alternative="two-sided")
            if p < alpha:
                significant += 1
        except Exception:
            pass
    return significant >= 2


def fisher_combine(p_values: list[float]) -> tuple[float, float]:
    """Fisher's method for combining p-values (assumes independence)."""
    if not p_values:
        return 0.0, 1.0
    clipped = [max(min(p, 1.0 - 1e-16), 1e-16) for p in p_values]
    stat, combined_p = stats.combine_pvalues(clipped, method="fisher")
    return float(stat), float(combined_p)


def legacy_fisher_batch_alert(
    baseline_fps: list[BehavioralFingerprint],
    current_fps: list[BehavioralFingerprint],
    alpha: float = 0.05,
    metrics: tuple[str, ...] = BATCH_METRICS,
) -> bool:
    """Pre-CCT batch rule: Mann-Whitney + BH + Fisher omnibus (independence assumed)."""
    if len(baseline_fps) < 3 or len(current_fps) < 3:
        return False

    raw_p: dict[str, float] = {}
    for metric in metrics:
        b_vals = [float(getattr(fp, metric)) for fp in baseline_fps]
        c_vals = [float(getattr(fp, metric)) for fp in current_fps]
        try:
            _, p = stats.mannwhitneyu(b_vals, c_vals, alternative="two-sided")
            raw_p[metric] = float(p)
        except Exception:
            raw_p[metric] = 1.0

    bh = benjamini_hochberg(raw_p, alpha=alpha)
    rejected_raw_ps = [raw_p[m] for m in metrics if bh.get(m, (1.0, False))[1]]
    quality_rejected = [m for m in metrics if bh.get(m, (1.0, False))[1] and m in QUALITY_METRICS]
    length_only = rejected_raw_ps and all(m in LENGTH_METRICS for m, (_, rej) in bh.items() if rej)

    if not rejected_raw_ps or length_only or not quality_rejected:
        return False

    _, fisher_p = fisher_combine(rejected_raw_ps)
    return fisher_p < alpha
