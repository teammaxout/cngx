"""Unit tests for drift detection."""

from datetime import datetime, timedelta

import pytest

from cogscope.core.models import BehavioralFingerprint, SignificanceLevel
from cogscope.drift.detector import DriftDetector
from cogscope.drift.scoring import DriftScorer


@pytest.fixture
def mock_fingerprint():
    """Create a sample fingerprint for testing."""
    return BehavioralFingerprint(
        trace_id="trace_test_123",
        task_id="test_task",
        timestamp=datetime.utcnow(),
        model="mock-model",
        depth=3,
        branching_factor=0.5,
        total_steps=3,
        max_step_length=50,
        tool_call_count=1,
        tool_call_sequence=["calculator"],
        tool_diversity=1.0,
        tool_success_rate=1.0,
        output_length=15,
        reasoning_length=50,
        compression_ratio=0.3,
        avg_sentence_length=5.0,
        correction_count=0,
        backtrack_count=0,
        revision_count=0,
        uncertainty_markers=0,
        confidence_markers=1,
        hedging_ratio=0.0,
        verification_steps=1,
        example_count=0,
        structured_output=False,
        tokens_per_step=10.0,
        reasoning_overhead=0.5,
    )


class TestDriftScorer:
    """Tests for DriftScorer."""

    def test_z_score_drift_basic(self):
        """Test basic z-score calculation."""
        scorer = DriftScorer()

        baseline_values = [5.0, 5.1, 4.9, 5.0, 5.2]
        current_value = 5.0

        z_score, p_value = scorer.z_score_drift(baseline_values, current_value)

        # Value matches mean, should have low z-score
        assert abs(z_score) < 1.0

    def test_z_score_drift_outlier(self):
        """Test z-score detection of outlier."""
        scorer = DriftScorer()

        baseline_values = [5.0, 5.1, 4.9, 5.0, 5.2]
        current_value = 10.0  # Clear outlier

        z_score, p_value = scorer.z_score_drift(baseline_values, current_value)

        assert z_score > 2.0
        assert p_value < 0.05

    def test_trend_detection_stable(self):
        """Test trend detection with stable values."""
        scorer = DriftScorer()

        values = [5.0, 5.1, 4.9, 5.0, 5.2, 4.8, 5.1]
        result = scorer.trend_detection(values)

        assert result["direction"] == "stable"

    def test_trend_detection_increasing(self):
        """Test trend detection with increasing values."""
        scorer = DriftScorer()

        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        result = scorer.trend_detection(values)

        assert result["direction"] == "increasing"
        assert result["slope"] > 0

    def test_trend_detection_decreasing(self):
        """Test trend detection with decreasing values."""
        scorer = DriftScorer()

        values = [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
        result = scorer.trend_detection(values)

        assert result["direction"] == "decreasing"
        assert result["slope"] < 0

    def test_compute_aggregate_drift(self):
        """Test aggregate drift computation."""
        scorer = DriftScorer()

        metric_scores = {
            "depth": 0.2,
            "correction_count": 0.8,
            "verification_steps": 0.9,
        }

        aggregate = scorer.compute_aggregate_drift(metric_scores)
        assert 0 <= aggregate <= 1

    def test_population_drift(self):
        """Test population drift comparison."""
        scorer = DriftScorer()

        # Create baseline population
        baseline_fps = []
        for i in range(10):
            fp = BehavioralFingerprint(
                trace_id=f"baseline_{i}",
                task_id="test",
                depth=5,
                total_steps=5,
                tool_call_count=2,
                correction_count=1,
                uncertainty_markers=2,
                verification_steps=2,
                hedging_ratio=0.3,
            )
            baseline_fps.append(fp)

        # Create current population with changes
        current_fps = []
        for i in range(10):
            fp = BehavioralFingerprint(
                trace_id=f"current_{i}",
                task_id="test",
                depth=3,  # Changed
                total_steps=3,
                tool_call_count=4,  # Changed
                correction_count=0,  # Changed
                uncertainty_markers=5,  # Changed
                verification_steps=0,  # Changed
                hedging_ratio=0.7,  # Changed
            )
            current_fps.append(fp)

        drift_scores = scorer.population_drift(baseline_fps, current_fps)

        # Should detect significant drift in changed metrics
        assert drift_scores.get("depth", 0) > 0.5
        assert drift_scores.get("verification_steps", 0) > 0.5


class TestDriftDetector:
    """Tests for DriftDetector."""

    def test_quick_check_stable(self, mock_fingerprint):
        """Test quick check with stable behavior."""
        detector = DriftDetector()

        # Same fingerprint should be stable
        score, status = detector.quick_check(mock_fingerprint, mock_fingerprint)

        assert score < 0.1
        assert "stable" in status.lower()

    def test_quick_check_drift(self):
        """Test quick check with drifting behavior."""
        detector = DriftDetector()

        baseline = BehavioralFingerprint(
            trace_id="baseline",
            task_id="test",
            depth=5,
            verification_steps=3,
            hedging_ratio=0.2,
        )

        current = BehavioralFingerprint(
            trace_id="current",
            task_id="test",
            depth=1,
            verification_steps=0,
            hedging_ratio=0.9,
        )

        score, status = detector.quick_check(current, baseline)

        assert score > 0.3
        assert "drift" in status.lower()

    def test_score_to_significance(self):
        """Test score to significance conversion."""
        detector = DriftDetector()

        assert detector._score_to_significance(0.96) == SignificanceLevel.CRITICAL
        assert detector._score_to_significance(0.91) == SignificanceLevel.MAJOR
        assert detector._score_to_significance(0.81) == SignificanceLevel.MODERATE
        assert detector._score_to_significance(0.51) == SignificanceLevel.MINOR
        assert detector._score_to_significance(0.3) == SignificanceLevel.NONE
