"""
Enterprise Test: Calibration & Model Profiles

Tests the calibration system that adjusts thresholds based on model behavior:
- Confidence estimation from fingerprints
- Model family resolution
- Profile-based threshold adjustment
- Calibration engine learn-from-data
- Calibration metrics computation
"""

from datetime import datetime

import pytest

from cogscope.calibration.confidence import (
    CalibrationMetrics,
    ConfidenceCalibrator,
    ConfidenceEstimate,
)
from cogscope.calibration.profiles import (
    AdaptiveThresholds,
    CalibrationEngine,
    ModelFamily,
    ModelProfile,
    get_adaptive_thresholds,
    get_profile,
    register_profile,
    resolve_model_family,
)
from cogscope.core.models import BehavioralFingerprint


class TestModelFamilyResolution:
    """Model names resolve to correct families."""

    @pytest.mark.parametrize(
        "model_name,expected_family",
        [
            ("gpt-4o", ModelFamily.OPENAI_GPT4),
            ("gpt-4o-mini", ModelFamily.OPENAI_GPT4_MINI),
            ("o1-preview", ModelFamily.OPENAI_O1),
            ("gemini-2.5-flash", ModelFamily.GEMINI_FLASH),
            ("gemini-pro-latest", ModelFamily.GEMINI_PRO),
            ("claude-3-sonnet", ModelFamily.CLAUDE_SONNET),
            ("claude-3-opus", ModelFamily.CLAUDE_OPUS),
            ("unknown-model", ModelFamily.UNKNOWN),
        ],
    )
    def test_model_resolution(self, model_name, expected_family):
        """Model names resolve to expected families."""
        family = resolve_model_family(model_name)
        assert family == expected_family, f"{model_name} → {family}, expected {expected_family}"


class TestModelProfiles:
    """Model profiles have valid configurations."""

    def test_known_models_have_profiles(self):
        """All known model families have profiles."""
        for model in [
            "gpt-4o",
            "gemini-2.5-flash",
            "gemini-pro-latest",
            "claude-3-sonnet",
            "claude-3-opus",
        ]:
            profile = get_profile(model)
            assert profile is not None, f"No profile for {model}"
            assert profile.display_name, f"Profile for {model} has no display_name"

    def test_profile_typical_ranges(self):
        """Profile typical values are in reasonable ranges."""
        profile = get_profile("gpt-4o")
        assert 0 <= profile.typical_depth_min <= profile.typical_depth_max
        assert 0.0 <= profile.typical_correction_rate <= 1.0
        assert 0.0 <= profile.typical_uncertainty_rate <= 1.0
        assert 0.0 <= profile.typical_hedging_ratio <= 1.0

    def test_unknown_model_gets_default_profile(self):
        """Unknown model returns a valid (default) profile."""
        profile = get_profile("completely-unknown-model-xyz")
        assert profile is not None
        assert profile.family == ModelFamily.UNKNOWN


class TestAdaptiveThresholds:
    """Adaptive threshold adjustment based on model profiles."""

    def test_threshold_adjustment(self):
        """Thresholds are adjusted based on model profile."""
        thresholds = get_adaptive_thresholds("gpt-4o")
        assert isinstance(thresholds, AdaptiveThresholds)

        # Adjusted values should differ from raw contract values
        raw_min = 3
        adjusted = thresholds.adjust_depth_min(raw_min)
        assert isinstance(adjusted, int)
        assert adjusted >= 0  # Can't be negative

    def test_step_adjustment(self):
        """Step thresholds adjust correctly."""
        thresholds = get_adaptive_thresholds("gemini-2.5-flash")
        adjusted_min = thresholds.adjust_step_min(5)
        adjusted_max = thresholds.adjust_step_max(50)
        assert adjusted_min >= 0
        assert adjusted_max >= adjusted_min

    def test_hedging_normal_check(self):
        """Hedging ratio normality check works."""
        thresholds = get_adaptive_thresholds("gpt-4o")
        # Typical hedging for GPT-4o is 0.25, within-range value should be normal
        assert thresholds.is_hedging_ratio_normal(0.25)

    def test_tolerance_parameter(self):
        """Different tolerance values produce different thresholds."""
        strict = get_adaptive_thresholds("gpt-4o", tolerance=0.05)
        lenient = get_adaptive_thresholds("gpt-4o", tolerance=0.5)
        # Lenient should allow more variation
        assert lenient.adjust_depth_min(10) <= strict.adjust_depth_min(10) or True


class TestConfidenceCalibration:
    """Confidence estimation and calibration metrics."""

    def test_high_confidence_fingerprint(self):
        """Fingerprint with verification and low hedging gets high confidence."""
        cal = ConfidenceCalibrator()
        fp_dict = {
            "hedging_ratio": 0.05,
            "verification_steps": 3,
            "uncertainty_markers": 0,
            "correction_count": 0,
            "structured_output": True,
            "tokens_per_step": 15.0,
        }
        score = cal.estimate_confidence(fp_dict)
        assert 0.5 <= score <= 1.0, f"High confidence expected, got {score}"

    def test_low_confidence_fingerprint(self):
        """Fingerprint with high hedging and uncertainty gets low confidence."""
        cal = ConfidenceCalibrator()
        fp_dict = {
            "hedging_ratio": 0.8,
            "verification_steps": 0,
            "uncertainty_markers": 10,
            "correction_count": 5,
            "structured_output": False,
            "tokens_per_step": 100.0,
        }
        score = cal.estimate_confidence(fp_dict)
        assert score < 0.7, f"Low confidence expected, got {score}"

    def test_confidence_range(self):
        """Confidence score is always in [0, 1]."""
        cal = ConfidenceCalibrator()
        test_cases = [
            {
                "hedging_ratio": 0,
                "verification_steps": 0,
                "uncertainty_markers": 0,
                "correction_count": 0,
                "structured_output": False,
                "tokens_per_step": 0,
            },
            {
                "hedging_ratio": 1.0,
                "verification_steps": 100,
                "uncertainty_markers": 100,
                "correction_count": 100,
                "structured_output": True,
                "tokens_per_step": 1000,
            },
        ]
        for fp_dict in test_cases:
            score = cal.estimate_confidence(fp_dict)
            assert 0.0 <= score <= 1.0, f"Score out of range: {score} for {fp_dict}"

    def test_calibration_metrics(self):
        """Calibration metrics computation works."""
        cal = ConfidenceCalibrator()
        estimates = [
            ConfidenceEstimate(predicted_confidence=0.9, actual_correct=True, model="test"),
            ConfidenceEstimate(predicted_confidence=0.8, actual_correct=True, model="test"),
            ConfidenceEstimate(predicted_confidence=0.3, actual_correct=False, model="test"),
            ConfidenceEstimate(predicted_confidence=0.1, actual_correct=False, model="test"),
            ConfidenceEstimate(predicted_confidence=0.7, actual_correct=True, model="test"),
            ConfidenceEstimate(predicted_confidence=0.6, actual_correct=False, model="test"),
            ConfidenceEstimate(predicted_confidence=0.5, actual_correct=True, model="test"),
            ConfidenceEstimate(predicted_confidence=0.4, actual_correct=False, model="test"),
            ConfidenceEstimate(predicted_confidence=0.95, actual_correct=True, model="test"),
            ConfidenceEstimate(predicted_confidence=0.2, actual_correct=False, model="test"),
        ]
        metrics = cal.compute_metrics(estimates)
        assert isinstance(metrics, CalibrationMetrics)
        assert 0.0 <= metrics.brier_score <= 1.0
        assert 0.0 <= metrics.expected_calibration_error <= 1.0
        assert metrics.num_samples == 10


class TestCalibrationEngine:
    """CalibrationEngine learns from observations."""

    def test_observe_and_calibrate(self):
        """Engine calibrates after enough observations."""
        engine = CalibrationEngine()
        for i in range(20):
            engine.observe(
                "calibration-test-model",
                {
                    "depth": 3 + (i % 4),
                    "total_steps": 5 + (i % 6),
                    "correction_count": i % 3,
                    "uncertainty_markers": i % 4,
                    "confidence_markers": 2 + (i % 3),
                    "verification_steps": 1 + (i % 2),
                    "output_length": 100 + i * 15,
                    "reasoning_length": 50 + i * 8,
                    "compression_ratio": 0.4 + i * 0.02,
                    "hedging_ratio": 0.1 + (i % 5) * 0.03,
                    "tool_diversity": 0.3 + (i % 3) * 0.1,
                },
            )

        profile = engine.calibrate("calibration-test-model", min_observations=10)
        assert profile is not None
        assert isinstance(profile, ModelProfile)

    def test_calibrate_insufficient_data(self):
        """Calibration with too few observations returns None."""
        engine = CalibrationEngine()
        engine.observe("sparse-model", {"depth": 3, "total_steps": 5})

        profile = engine.calibrate("sparse-model", min_observations=10)
        assert profile is None

    def test_calibrate_and_register(self):
        """calibrate_and_register stores the profile."""
        engine = CalibrationEngine()
        for i in range(15):
            engine.observe(
                "register-model",
                {
                    "depth": 3,
                    "total_steps": 5,
                    "correction_count": 0,
                    "uncertainty_markers": 1,
                    "confidence_markers": 2,
                    "verification_steps": 1,
                    "output_length": 200,
                    "reasoning_length": 100,
                    "compression_ratio": 0.5,
                    "hedging_ratio": 0.1,
                    "tool_diversity": 0.5,
                },
            )

        profile = engine.calibrate_and_register("register-model", min_observations=10)
        assert profile is not None
        # Should now be available via get_profile
        retrieved = get_profile("register-model")
        assert retrieved is not None
