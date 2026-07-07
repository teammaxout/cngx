"""Tests for statistically honest drift alerting."""

from datetime import datetime

import pytest

from cogscope.calibration.profiles import get_adaptive_thresholds
from cogscope.core.models import BehavioralFingerprint
from cogscope.drift.detector import DriftDetector


def _fp(**overrides) -> BehavioralFingerprint:
    defaults = dict(
        trace_id="t1",
        task_id="math",
        timestamp=datetime.utcnow(),
        model="gpt-4o-mini",
        depth=5,
        branching_factor=0.5,
        total_steps=5,
        max_step_length=80,
        tool_call_count=0,
        tool_call_sequence=[],
        tool_diversity=0.0,
        tool_success_rate=1.0,
        output_length=2000,
        reasoning_length=4000,
        compression_ratio=0.5,
        avg_sentence_length=20.0,
        correction_count=1,
        backtrack_count=0,
        revision_count=0,
        uncertainty_markers=1,
        confidence_markers=2,
        hedging_ratio=0.2,
        verification_steps=3,
        example_count=0,
        structured_output=False,
        tokens_per_step=10.0,
        reasoning_overhead=0.5,
    )
    defaults.update(overrides)
    return BehavioralFingerprint(**defaults)


class TestStatisticalDriftAlerting:
    """Prove shorter-but-normal responses do not false-alarm."""

    def test_shorter_concise_response_does_not_alert(self):
        """Shorter output inside baseline distribution must NOT trigger drift."""
        baseline = _fp(trace_id="baseline")
        history = [
            _fp(trace_id=f"h{i}", output_length=1950 + (i % 3) * 50, depth=5, verification_steps=3)
            for i in range(12)
        ]

        current = _fp(
            trace_id="current",
            output_length=1200,
            reasoning_length=2400,
            compression_ratio=0.5,
            depth=5,
            verification_steps=3,
            correction_count=1,
            total_steps=5,
        )

        detector = DriftDetector()
        result = detector.assess_against_pinned_baseline(
            current, baseline, history, baseline_name="math_v1"
        )

        assert result.should_alert is False, (
            f"False positive: {result.summary} outliers={result.outliers}"
        )

    def test_quality_regression_does_alert(self):
        """Dropping verification AND depth together should alert."""
        baseline = _fp(trace_id="baseline")
        history = [
            _fp(trace_id=f"h{i}", depth=5, verification_steps=3, output_length=2000)
            for i in range(12)
        ]
        current = _fp(trace_id="bad", depth=1, verification_steps=0, output_length=2000)

        detector = DriftDetector()
        result = detector.assess_against_pinned_baseline(
            current, baseline, history, baseline_name="math_v1"
        )

        assert result.should_alert is True
        quality_outliers = [o for o in result.outliers if o["is_quality"]]
        assert len(quality_outliers) >= 1

    def test_adaptive_thresholds_length_only_not_outlier_enough(self):
        thresholds = get_adaptive_thresholds("gpt-4o-mini")
        history = [_fp(trace_id=f"h{i}", output_length=2000) for i in range(10)]
        dist = thresholds.build_metric_distribution(history)
        current = _fp(output_length=1200, depth=5, verification_steps=3)
        should_alert, outliers = thresholds.is_multimetric_outlier(current, dist)
        assert should_alert is False
        length_outliers = [o for o in outliers if o["is_length"]]
        assert len(length_outliers) <= 1
