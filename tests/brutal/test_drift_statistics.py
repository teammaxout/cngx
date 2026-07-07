"""
BRUTAL TEST: Drift Detection Statistical Validity

Tests whether the drift detection actually uses proper statistics
and produces meaningful results on known distributions.
"""

import numpy as np
import pytest

from cogscope.drift.detector import DriftDetector
from cogscope.drift.scoring import DriftScorer
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database
from tests.brutal.conftest import make_trace
from tests.brutal.fixtures.sample_outputs import (
    GOOD_MATH_REASONING,
    HEDGING_RESPONSE,
    SHALLOW_MATH,
)


class TestDriftScorerStatistics:
    """Test the statistical methods in drift scoring."""

    def setup_method(self):
        self.scorer = DriftScorer()

    # ------------------------------------------------------------------ z-score
    def test_no_drift_on_identical_values(self):
        """Identical baseline and current values should show no drift."""
        z, p = self.scorer.z_score_drift(
            baseline_values=[1.0, 1.0, 1.0, 1.0, 1.0],
            current_value=1.0,
        )
        assert z == 0.0 or abs(z) < 0.01, f"Identical values should have z-score ≈ 0, got {z}"

    def test_drift_on_outlier(self):
        """Value far from baseline distribution should show high drift."""
        z, p = self.scorer.z_score_drift(
            baseline_values=[1.0, 1.1, 0.9, 1.0, 1.05],
            current_value=5.0,
        )
        assert abs(z) > 2.0, f"Outlier should have |z-score| > 2, got {z}"

    def test_z_score_p_value_for_outlier(self):
        """P-value for outlier should be small."""
        z, p = self.scorer.z_score_drift(
            baseline_values=[1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.02, 0.98],
            current_value=5.0,
        )
        assert p < 0.05, f"Outlier should have p < 0.05, got {p}"

    def test_z_score_small_sample(self):
        """With < 2 values, should return safe defaults."""
        z, p = self.scorer.z_score_drift(
            baseline_values=[1.0],
            current_value=5.0,
        )
        assert z == 0.0 and p == 1.0, "Single-value baseline should return defaults"

    # ---------------------------------------------------------- trend detection
    def test_trend_detection_increasing(self):
        """Steadily increasing values should detect upward trend."""
        result = self.scorer.trend_detection(
            values=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        )
        assert (
            result["slope"] > 0
        ), f"Increasing values should have positive slope, got {result['slope']}"
        assert result["direction"] == "increasing"

    def test_trend_detection_flat(self):
        """Flat values should show no significant trend."""
        result = self.scorer.trend_detection(
            values=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
        )
        assert (
            abs(result["slope"]) < 0.01
        ), f"Flat values should have slope ≈ 0, got {result['slope']}"
        assert result["direction"] == "stable"

    def test_trend_detection_noisy_but_flat(self):
        """Noisy but mean-stable values should not flag a trend."""
        np.random.seed(42)
        values = list(np.random.normal(5.0, 0.1, 20))
        result = self.scorer.trend_detection(values=values)
        assert (
            abs(result["slope"]) < 0.5
        ), f"Noisy-but-flat values should have small slope, got {result['slope']}"

    def test_trend_detection_decreasing(self):
        """Decreasing values should detect downward trend."""
        result = self.scorer.trend_detection(
            values=[10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
        )
        assert result["slope"] < 0
        assert result["direction"] == "decreasing"

    def test_trend_short_series(self):
        """Too-short series should return stable safely."""
        result = self.scorer.trend_detection(values=[1.0, 2.0])
        assert result["direction"] == "stable"
        assert result["slope"] == 0.0

    # ------------------------------------------------------- aggregate scoring
    def test_aggregate_drift_score(self):
        """Aggregate drift should combine multiple metrics meaningfully."""
        metrics = {"depth": 0.9, "hedging_ratio": 0.8}
        score = self.scorer.compute_aggregate_drift(metrics)
        assert score > 0, "High metric scores should produce positive aggregate drift"

    def test_aggregate_empty(self):
        """Empty metrics should return 0.0."""
        score = self.scorer.compute_aggregate_drift({})
        assert score == 0.0

    def test_aggregate_single_zero(self):
        """Single zero-score metric should return near zero."""
        score = self.scorer.compute_aggregate_drift({"depth": 0.0})
        assert score < 0.01


class TestDriftDetectorWithRealData:
    """Test drift detector with fingerprints from known-different outputs."""

    def test_drift_low_for_consistent_behavior(self, fresh_db):
        """Consistent outputs should show low drift."""
        extractor = FingerprintExtractor()
        # Store 10 fingerprints from same output
        for i in range(10):
            trace = make_trace(
                GOOD_MATH_REASONING,
                task_id="consistent",
                trace_id=f"cons_{i:03d}",
            )
            fresh_db.save_trace(trace)
            fp = extractor.extract(trace)
            fresh_db.save_fingerprint(fp)

        detector = DriftDetector(fresh_db)
        report = detector.detect_drift(task_id="consistent")
        assert report is not None
        assert (
            report.drift_score < 0.3
        ), f"Consistent behavior drift should be < 0.3, got {report.drift_score}"

    def test_drift_detected_on_behavior_change(self, fresh_db):
        """If behavior changes mid-stream, drift should be detected."""
        extractor = FingerprintExtractor()
        # First 5: good reasoning
        for i in range(5):
            trace = make_trace(
                GOOD_MATH_REASONING,
                task_id="changing",
                trace_id=f"good_{i:03d}",
            )
            fresh_db.save_trace(trace)
            fp = extractor.extract(trace)
            fresh_db.save_fingerprint(fp)

        # Next 5: shallow reasoning (simulating regression)
        for i in range(5):
            trace = make_trace(
                SHALLOW_MATH,
                task_id="changing",
                trace_id=f"shallow_{i:03d}",
            )
            fresh_db.save_trace(trace)
            fp = extractor.extract(trace)
            fresh_db.save_fingerprint(fp)

        detector = DriftDetector(fresh_db)
        report = detector.detect_drift(task_id="changing")
        assert report is not None
        assert (
            report.drift_score > 0.0
        ), f"Behavior change should produce some drift, got {report.drift_score}"
