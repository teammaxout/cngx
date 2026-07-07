"""Drift scoring algorithms."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats

from cogscope.core.models import BehavioralFingerprint


class DriftScorer:
    """Statistical scoring for drift detection.

    Implements various algorithms for measuring how much
    behavior has drifted from a baseline.
    """

    def __init__(self):
        pass

    def z_score_drift(
        self,
        baseline_values: list[float],
        current_value: float,
    ) -> tuple[float, float]:
        """Calculate z-score based drift.

        Args:
            baseline_values: Historical values
            current_value: Current value to test

        Returns:
            (z_score, p_value)
        """
        if len(baseline_values) < 2:
            return 0.0, 1.0

        mean = np.mean(baseline_values)
        std = np.std(baseline_values)

        if std == 0:
            return 0.0, 1.0

        z_score = (current_value - mean) / std
        p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))

        return float(z_score), float(p_value)

    def population_drift(
        self,
        baseline_fingerprints: list[BehavioralFingerprint],
        current_fingerprints: list[BehavioralFingerprint],
    ) -> dict[str, float]:
        """Compare two populations of fingerprints for drift.

        Uses Mann-Whitney U test for non-parametric comparison.

        Args:
            baseline_fingerprints: Historical fingerprints
            current_fingerprints: Recent fingerprints

        Returns:
            Dict of metric -> drift score
        """
        if len(baseline_fingerprints) < 3 or len(current_fingerprints) < 3:
            return {}

        # Metrics to compare
        metrics = [
            "depth",
            "total_steps",
            "tool_call_count",
            "correction_count",
            "uncertainty_markers",
            "verification_steps",
            "hedging_ratio",
        ]

        drift_scores = {}

        for metric in metrics:
            baseline_vals = [getattr(fp, metric) for fp in baseline_fingerprints]
            current_vals = [getattr(fp, metric) for fp in current_fingerprints]

            try:
                stat, p_value = stats.mannwhitneyu(
                    baseline_vals, current_vals, alternative="two-sided"
                )
                drift_scores[metric] = float(1 - p_value)
            except Exception:
                drift_scores[metric] = 0.0

        return drift_scores

    def population_drift_batch(
        self,
        baseline_fingerprints: list[BehavioralFingerprint],
        current_fingerprints: list[BehavioralFingerprint],
        alpha: float = 0.05,
    ):
        """Mann-Whitney + BH + CCT batch test (preferred for diff/check)."""
        from cogscope.drift.batch import batch_drift_test

        return batch_drift_test(baseline_fingerprints, current_fingerprints, alpha=alpha)

    def trend_detection(
        self,
        values: list[float],
        timestamps: list[float] | None = None,
    ) -> dict[str, Any]:
        """Detect trend in a series of values.

        Args:
            values: Time-ordered values
            timestamps: Optional timestamps (uses index if None)

        Returns:
            Dict with trend info (direction, slope, significance)
        """
        if len(values) < 5:
            return {"direction": "stable", "slope": 0.0, "significance": 0.0}

        x = np.array(timestamps if timestamps else list(range(len(values))))
        y = np.array(values)

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Determine trend direction
        if p_value < 0.05:
            direction = "increasing" if slope > 0 else "decreasing"
        else:
            direction = "stable"

        return {
            "direction": direction,
            "slope": float(slope),
            "r_squared": float(r_value**2),
            "p_value": float(p_value),
            "significance": float(1 - p_value),
        }

    def compute_aggregate_drift(
        self,
        metric_scores: dict[str, float],
        weights: dict[str, float] | None = None,
    ) -> float:
        """Compute weighted aggregate drift score.

        Args:
            metric_scores: Individual metric drift scores
            weights: Optional weights per metric

        Returns:
            Aggregate drift score (0-1)
        """
        if not metric_scores:
            return 0.0

        default_weights = {
            "depth": 1.5,
            "total_steps": 1.2,
            "tool_call_count": 1.3,
            "correction_count": 1.8,
            "uncertainty_markers": 1.0,
            "verification_steps": 1.6,
            "hedging_ratio": 1.4,
        }

        weights = weights or default_weights

        weighted_sum = 0.0
        total_weight = 0.0

        for metric, score in metric_scores.items():
            w = weights.get(metric, 1.0)
            weighted_sum += w * score
            total_weight += w

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_sum / total_weight)
