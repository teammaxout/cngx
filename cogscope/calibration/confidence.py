"""Confidence calibration module.

Computes calibration metrics (Brier score, ECE, calibration curves)
for model confidence estimates derived from behavioral fingerprints.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("cogscope.calibration.confidence")


@dataclass
class CalibrationMetrics:
    """Calibration metrics for a set of predictions."""

    brier_score: float  # 0.0 (perfect) to 1.0 (worst)
    expected_calibration_error: float  # ECE
    maximum_calibration_error: float  # MCE
    overconfidence_ratio: float  # % predictions with confidence > accuracy
    underconfidence_ratio: float  # % predictions with confidence < accuracy
    curve_data: list[dict] = field(default_factory=list)  # Calibration curve
    num_samples: int = 0
    num_bins: int = 10
    details: dict = field(default_factory=dict)


@dataclass
class ConfidenceEstimate:
    """A single confidence estimate with ground truth."""

    predicted_confidence: float  # Model's estimated confidence (0-1)
    actual_correct: bool  # Ground truth: was the answer correct?
    model: str = ""
    task_id: str = ""


class ConfidenceCalibrator:
    """Compute calibration metrics for model confidence estimates.

    Confidence is derived from observable behavioral signals:
    - Hedging ratio (lower hedging → higher confidence)
    - Verification steps (more verification → higher confidence)
    - Uncertainty markers (fewer → higher confidence)
    - Consistency across paraphrases

    This module measures how well those confidence signals
    correlate with actual correctness.
    """

    def __init__(self, num_bins: int = 10):
        self.num_bins = num_bins

    def compute_metrics(
        self,
        estimates: list[ConfidenceEstimate],
    ) -> CalibrationMetrics:
        """Compute full calibration metrics.

        Args:
            estimates: List of confidence estimates with ground truth

        Returns:
            CalibrationMetrics with Brier score, ECE, etc.
        """
        if not estimates:
            return CalibrationMetrics(
                brier_score=0.0,
                expected_calibration_error=0.0,
                maximum_calibration_error=0.0,
                overconfidence_ratio=0.0,
                underconfidence_ratio=0.0,
                num_samples=0,
            )

        n = len(estimates)

        # Brier score
        brier = self._brier_score(estimates)

        # Binned calibration
        bins = self._bin_estimates(estimates)
        ece = self._expected_calibration_error(bins, n)
        mce = self._maximum_calibration_error(bins)

        # Over/under confidence
        overconf, underconf = self._confidence_bias(bins)

        # Calibration curve data
        curve_data = self._calibration_curve(bins)

        return CalibrationMetrics(
            brier_score=brier,
            expected_calibration_error=ece,
            maximum_calibration_error=mce,
            overconfidence_ratio=overconf,
            underconfidence_ratio=underconf,
            curve_data=curve_data,
            num_samples=n,
            num_bins=self.num_bins,
            details={
                "mean_confidence": statistics.mean(e.predicted_confidence for e in estimates),
                "mean_accuracy": sum(1 for e in estimates if e.actual_correct) / n,
                "bins_with_data": sum(1 for b in bins if b["count"] > 0),
            },
        )

    def estimate_confidence(
        self,
        fingerprint: dict,
        output: str = "",
    ) -> float:
        """Estimate confidence from behavioral fingerprint.

        Uses observable signals to estimate how confident
        the model was in its answer.
        """
        signals = []

        # Hedging ratio: lower hedging → higher confidence
        hedging = fingerprint.get("hedging_ratio", 0.5)
        signals.append(1.0 - min(1.0, hedging))

        # Verification steps: more verification → higher confidence
        verification = fingerprint.get("verification_steps", 0)
        signals.append(min(1.0, verification * 0.2))

        # Uncertainty markers: fewer → higher confidence
        uncertainty = fingerprint.get("uncertainty_markers", 0)
        confidence_markers = fingerprint.get("confidence_markers", 0)
        total_markers = uncertainty + confidence_markers
        if total_markers > 0:
            signals.append(confidence_markers / total_markers)
        else:
            signals.append(0.5)

        # Correction count: fewer corrections → higher confidence
        corrections = fingerprint.get("correction_count", 0)
        signals.append(max(0.0, 1.0 - corrections * 0.15))

        # Structured output: structured → higher confidence
        if fingerprint.get("structured_output"):
            signals.append(0.8)
        else:
            signals.append(0.5)

        # Output length consistency
        depth = fingerprint.get("depth", 1)
        if depth > 0:
            tokens_per_step = fingerprint.get("tokens_per_step", 50)
            # Very consistent step length → higher confidence
            if 20 < tokens_per_step < 200:
                signals.append(0.7)
            else:
                signals.append(0.4)

        return statistics.mean(signals) if signals else 0.5

    def _brier_score(self, estimates: list[ConfidenceEstimate]) -> float:
        """Compute Brier score: mean squared error of confidence vs outcome.

        Brier = (1/N) * Σ(confidence_i - outcome_i)²
        where outcome_i is 1 if correct, 0 otherwise.
        """
        return statistics.mean(
            (e.predicted_confidence - (1.0 if e.actual_correct else 0.0)) ** 2 for e in estimates
        )

    def _bin_estimates(self, estimates: list[ConfidenceEstimate]) -> list[dict]:
        """Bin estimates by confidence level."""
        bins = [
            {
                "lower": i / self.num_bins,
                "upper": (i + 1) / self.num_bins,
                "confidences": [],
                "accuracies": [],
                "count": 0,
            }
            for i in range(self.num_bins)
        ]

        for e in estimates:
            bin_idx = min(
                int(e.predicted_confidence * self.num_bins),
                self.num_bins - 1,
            )
            bins[bin_idx]["confidences"].append(e.predicted_confidence)
            bins[bin_idx]["accuracies"].append(1.0 if e.actual_correct else 0.0)
            bins[bin_idx]["count"] += 1

        # Compute bin statistics
        for b in bins:
            if b["count"] > 0:
                b["mean_confidence"] = statistics.mean(b["confidences"])
                b["mean_accuracy"] = statistics.mean(b["accuracies"])
                b["calibration_gap"] = abs(b["mean_confidence"] - b["mean_accuracy"])
            else:
                b["mean_confidence"] = (b["lower"] + b["upper"]) / 2
                b["mean_accuracy"] = 0.0
                b["calibration_gap"] = 0.0

        return bins

    def _expected_calibration_error(self, bins: list[dict], total: int) -> float:
        """Compute Expected Calibration Error (ECE).

        ECE = Σ (|B_m|/N) * |acc(B_m) - conf(B_m)|
        """
        if total == 0:
            return 0.0
        return sum((b["count"] / total) * b["calibration_gap"] for b in bins if b["count"] > 0)

    def _maximum_calibration_error(self, bins: list[dict]) -> float:
        """Compute Maximum Calibration Error (MCE)."""
        gaps = [b["calibration_gap"] for b in bins if b["count"] > 0]
        return max(gaps) if gaps else 0.0

    def _confidence_bias(self, bins: list[dict]) -> tuple[float, float]:
        """Compute overconfidence and underconfidence ratios."""
        total_bins = sum(1 for b in bins if b["count"] > 0)
        if total_bins == 0:
            return 0.0, 0.0

        overconf = sum(
            1 for b in bins if b["count"] > 0 and b["mean_confidence"] > b["mean_accuracy"]
        )
        underconf = sum(
            1 for b in bins if b["count"] > 0 and b["mean_confidence"] < b["mean_accuracy"]
        )

        return overconf / total_bins, underconf / total_bins

    def _calibration_curve(self, bins: list[dict]) -> list[dict]:
        """Generate calibration curve data points."""
        return [
            {
                "bin_lower": b["lower"],
                "bin_upper": b["upper"],
                "mean_predicted": b["mean_confidence"],
                "mean_actual": b["mean_accuracy"],
                "count": b["count"],
                "gap": b["calibration_gap"],
            }
            for b in bins
            if b["count"] > 0
        ]
