"""Tests for cogscope.calibration module."""

import pytest

from cogscope.calibration.confidence import ConfidenceCalibrator, ConfidenceEstimate


class TestConfidenceCalibrator:
    def test_compute_metrics(self):
        cal = ConfidenceCalibrator()
        estimates = [
            ConfidenceEstimate(predicted_confidence=0.9, actual_correct=True),
            ConfidenceEstimate(predicted_confidence=0.8, actual_correct=True),
            ConfidenceEstimate(predicted_confidence=0.7, actual_correct=False),
            ConfidenceEstimate(predicted_confidence=0.5, actual_correct=True),
            ConfidenceEstimate(predicted_confidence=0.3, actual_correct=False),
            ConfidenceEstimate(predicted_confidence=0.2, actual_correct=False),
        ]
        metrics = cal.compute_metrics(estimates)
        assert 0 <= metrics.brier_score <= 1
        assert 0 <= metrics.expected_calibration_error <= 1
        assert 0 <= metrics.maximum_calibration_error <= 1

    def test_perfect_calibration(self):
        cal = ConfidenceCalibrator()
        # Perfect calibration: confident on correct, unconfident on wrong
        estimates = [
            ConfidenceEstimate(predicted_confidence=1.0, actual_correct=True),
            ConfidenceEstimate(predicted_confidence=0.0, actual_correct=False),
        ]
        metrics = cal.compute_metrics(estimates)
        assert metrics.brier_score == 0.0

    def test_estimate_confidence(self):
        cal = ConfidenceCalibrator()
        fp = {
            "hedging_ratio": 0.1,
            "verification_steps": 3,
            "depth": 5,
            "token_efficiency": 0.6,
            "correction_count": 0,
            "output_length": 200,
        }
        confidence = cal.estimate_confidence(fp)
        assert 0 <= confidence <= 1.0

    def test_overconfidence_detection(self):
        cal = ConfidenceCalibrator()
        # All high confidence but some wrong
        estimates = [
            ConfidenceEstimate(predicted_confidence=0.95, actual_correct=True),
            ConfidenceEstimate(predicted_confidence=0.90, actual_correct=False),
            ConfidenceEstimate(predicted_confidence=0.95, actual_correct=False),
            ConfidenceEstimate(predicted_confidence=0.85, actual_correct=True),
        ]
        metrics = cal.compute_metrics(estimates)
        assert metrics.overconfidence_ratio > 0

    def test_empty_estimates(self):
        cal = ConfidenceCalibrator()
        metrics = cal.compute_metrics([])
        assert metrics.brier_score == 0.0
        assert metrics.expected_calibration_error == 0.0
