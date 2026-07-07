"""Model behavioral profiles and adaptive threshold calibration.

DESIGN PRINCIPLE (alerting): Drift alerts must compare each response against
that model's own pinned baseline distribution — never against hardcoded universal
numbers. A shorter or more concise answer is not degradation by itself; only
multi-metric statistical outliers relative to the user's baseline history should
raise an alert.

Each model family has characteristic behavioral patterns. Contracts should
be evaluated relative to what's *normal* for a given model, not against
fixed universal thresholds.

Example: Gemini 2.5 Flash has verbose reasoning → higher baseline depth.
         GPT-4o-mini is concise → lower baseline depth.
         A depth-min=3 contract should mean different things for each.
"""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from cogscope.core.models import BehavioralFingerprint


class ModelFamily(str, Enum):
    """Known model families with distinct behavioral signatures."""

    OPENAI_GPT4 = "openai_gpt4"
    OPENAI_GPT4_MINI = "openai_gpt4_mini"
    OPENAI_O1 = "openai_o1"
    OPENAI_O3 = "openai_o3"
    GEMINI_FLASH = "gemini_flash"
    GEMINI_PRO = "gemini_pro"
    CLAUDE_SONNET = "claude_sonnet"
    CLAUDE_OPUS = "claude_opus"
    CLAUDE_HAIKU = "claude_haiku"
    LLAMA = "llama"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    UNKNOWN = "unknown"


@dataclass
class ModelProfile:
    """Behavioral baseline for a model family.

    These represent the *expected* behavioral characteristics of each model.
    Thresholds are adjusted relative to these baselines.
    """

    family: ModelFamily
    display_name: str

    # Expected depth range (reasoning steps)
    typical_depth_min: int = 2
    typical_depth_max: int = 15

    # Expected correction frequency (per 1000 tokens)
    typical_correction_rate: float = 0.5
    typical_uncertainty_rate: float = 1.0
    typical_confidence_rate: float = 0.8
    typical_verification_rate: float = 0.3

    # Output characteristics
    typical_output_length: int = 2000
    typical_reasoning_length: int = 5000
    typical_compression_ratio: float = 0.4

    # Hedging behavior
    typical_hedging_ratio: float = 0.3

    # Tool usage
    typical_tool_diversity: float = 0.5

    # Language patterns — different models use different phrasing
    correction_patterns: list[str] = field(default_factory=list)
    uncertainty_patterns: list[str] = field(default_factory=list)
    confidence_patterns: list[str] = field(default_factory=list)
    verification_patterns: list[str] = field(default_factory=list)

    # Whether this model supports extended thinking / reasoning tokens
    supports_reasoning_tokens: bool = False

    # Scaling factors for threshold adjustment
    depth_scale: float = 1.0
    step_scale: float = 1.0
    verification_scale: float = 1.0


# ---- Built-in profiles ----

_BUILTIN_PROFILES: dict[ModelFamily, ModelProfile] = {
    ModelFamily.OPENAI_GPT4: ModelProfile(
        family=ModelFamily.OPENAI_GPT4,
        display_name="GPT-4o / GPT-4 Turbo",
        typical_depth_min=3,
        typical_depth_max=12,
        typical_correction_rate=0.3,
        typical_uncertainty_rate=0.6,
        typical_confidence_rate=1.0,
        typical_verification_rate=0.4,
        typical_output_length=2500,
        typical_reasoning_length=0,  # No exposed reasoning
        typical_compression_ratio=1.0,
        typical_hedging_ratio=0.25,
        supports_reasoning_tokens=False,
        depth_scale=1.0,
        step_scale=1.0,
        verification_scale=1.0,
    ),
    ModelFamily.OPENAI_GPT4_MINI: ModelProfile(
        family=ModelFamily.OPENAI_GPT4_MINI,
        display_name="GPT-4o-mini",
        typical_depth_min=2,
        typical_depth_max=8,
        typical_correction_rate=0.2,
        typical_uncertainty_rate=0.8,
        typical_confidence_rate=0.6,
        typical_verification_rate=0.2,
        typical_output_length=1500,
        typical_reasoning_length=0,
        typical_compression_ratio=1.0,
        typical_hedging_ratio=0.35,
        supports_reasoning_tokens=False,
        depth_scale=0.7,
        step_scale=0.7,
        verification_scale=0.6,
    ),
    ModelFamily.OPENAI_O1: ModelProfile(
        family=ModelFamily.OPENAI_O1,
        display_name="o1 / o1-pro",
        typical_depth_min=5,
        typical_depth_max=30,
        typical_correction_rate=1.5,
        typical_uncertainty_rate=0.4,
        typical_confidence_rate=1.5,
        typical_verification_rate=1.2,
        typical_output_length=3000,
        typical_reasoning_length=15000,
        typical_compression_ratio=0.2,
        typical_hedging_ratio=0.15,
        supports_reasoning_tokens=True,
        depth_scale=2.0,
        step_scale=2.0,
        verification_scale=1.5,
    ),
    ModelFamily.OPENAI_O3: ModelProfile(
        family=ModelFamily.OPENAI_O3,
        display_name="o3 / o3-mini",
        typical_depth_min=5,
        typical_depth_max=25,
        typical_correction_rate=1.2,
        typical_uncertainty_rate=0.5,
        typical_confidence_rate=1.2,
        typical_verification_rate=1.0,
        typical_output_length=2500,
        typical_reasoning_length=12000,
        typical_compression_ratio=0.2,
        typical_hedging_ratio=0.2,
        supports_reasoning_tokens=True,
        depth_scale=1.8,
        step_scale=1.8,
        verification_scale=1.4,
    ),
    ModelFamily.GEMINI_FLASH: ModelProfile(
        family=ModelFamily.GEMINI_FLASH,
        display_name="Gemini 2.5 Flash",
        typical_depth_min=4,
        typical_depth_max=20,
        typical_correction_rate=0.8,
        typical_uncertainty_rate=0.7,
        typical_confidence_rate=0.9,
        typical_verification_rate=0.5,
        typical_output_length=3000,
        typical_reasoning_length=10000,
        typical_compression_ratio=0.3,
        typical_hedging_ratio=0.3,
        supports_reasoning_tokens=True,
        depth_scale=1.5,
        step_scale=1.5,
        verification_scale=1.2,
    ),
    ModelFamily.GEMINI_PRO: ModelProfile(
        family=ModelFamily.GEMINI_PRO,
        display_name="Gemini Pro / Ultra",
        typical_depth_min=3,
        typical_depth_max=15,
        typical_correction_rate=0.5,
        typical_uncertainty_rate=0.6,
        typical_confidence_rate=1.0,
        typical_verification_rate=0.4,
        typical_output_length=2500,
        typical_reasoning_length=8000,
        typical_compression_ratio=0.35,
        typical_hedging_ratio=0.25,
        supports_reasoning_tokens=True,
        depth_scale=1.2,
        step_scale=1.2,
        verification_scale=1.0,
    ),
    ModelFamily.CLAUDE_SONNET: ModelProfile(
        family=ModelFamily.CLAUDE_SONNET,
        display_name="Claude Sonnet",
        typical_depth_min=4,
        typical_depth_max=18,
        typical_correction_rate=0.6,
        typical_uncertainty_rate=0.5,
        typical_confidence_rate=1.1,
        typical_verification_rate=0.6,
        typical_output_length=3000,
        typical_reasoning_length=8000,
        typical_compression_ratio=0.35,
        typical_hedging_ratio=0.2,
        supports_reasoning_tokens=True,
        depth_scale=1.3,
        step_scale=1.3,
        verification_scale=1.2,
    ),
    ModelFamily.CLAUDE_OPUS: ModelProfile(
        family=ModelFamily.CLAUDE_OPUS,
        display_name="Claude Opus",
        typical_depth_min=5,
        typical_depth_max=25,
        typical_correction_rate=0.8,
        typical_uncertainty_rate=0.4,
        typical_confidence_rate=1.3,
        typical_verification_rate=0.8,
        typical_output_length=4000,
        typical_reasoning_length=12000,
        typical_compression_ratio=0.3,
        typical_hedging_ratio=0.15,
        supports_reasoning_tokens=True,
        depth_scale=1.7,
        step_scale=1.7,
        verification_scale=1.5,
    ),
    ModelFamily.CLAUDE_HAIKU: ModelProfile(
        family=ModelFamily.CLAUDE_HAIKU,
        display_name="Claude Haiku",
        typical_depth_min=2,
        typical_depth_max=10,
        typical_correction_rate=0.2,
        typical_uncertainty_rate=0.7,
        typical_confidence_rate=0.7,
        typical_verification_rate=0.2,
        typical_output_length=1500,
        typical_reasoning_length=3000,
        typical_compression_ratio=0.5,
        typical_hedging_ratio=0.35,
        supports_reasoning_tokens=True,
        depth_scale=0.7,
        step_scale=0.7,
        verification_scale=0.5,
    ),
    ModelFamily.LLAMA: ModelProfile(
        family=ModelFamily.LLAMA,
        display_name="Llama 3 / 3.1 / 4",
        typical_depth_min=2,
        typical_depth_max=10,
        typical_correction_rate=0.3,
        typical_uncertainty_rate=1.0,
        typical_confidence_rate=0.5,
        typical_verification_rate=0.2,
        typical_output_length=2000,
        typical_reasoning_length=0,
        typical_compression_ratio=1.0,
        typical_hedging_ratio=0.4,
        supports_reasoning_tokens=False,
        depth_scale=0.8,
        step_scale=0.8,
        verification_scale=0.5,
    ),
    ModelFamily.MISTRAL: ModelProfile(
        family=ModelFamily.MISTRAL,
        display_name="Mistral / Mixtral",
        typical_depth_min=2,
        typical_depth_max=10,
        typical_correction_rate=0.3,
        typical_uncertainty_rate=0.9,
        typical_confidence_rate=0.6,
        typical_verification_rate=0.2,
        typical_output_length=1800,
        typical_reasoning_length=0,
        typical_compression_ratio=1.0,
        typical_hedging_ratio=0.35,
        supports_reasoning_tokens=False,
        depth_scale=0.8,
        step_scale=0.8,
        verification_scale=0.5,
    ),
    ModelFamily.DEEPSEEK: ModelProfile(
        family=ModelFamily.DEEPSEEK,
        display_name="DeepSeek R1 / V3",
        typical_depth_min=4,
        typical_depth_max=20,
        typical_correction_rate=1.0,
        typical_uncertainty_rate=0.5,
        typical_confidence_rate=1.0,
        typical_verification_rate=0.7,
        typical_output_length=2500,
        typical_reasoning_length=10000,
        typical_compression_ratio=0.25,
        typical_hedging_ratio=0.2,
        supports_reasoning_tokens=True,
        depth_scale=1.5,
        step_scale=1.5,
        verification_scale=1.3,
    ),
}

# Add a generic unknown profile
_BUILTIN_PROFILES[ModelFamily.UNKNOWN] = ModelProfile(
    family=ModelFamily.UNKNOWN,
    display_name="Unknown Model",
)

# Custom profiles registered at runtime
_custom_profiles: dict[str, ModelProfile] = {}


# ---- Model name → family resolution ----

_MODEL_NAME_PATTERNS: list[tuple[re.Pattern, ModelFamily]] = [
    (re.compile(r"gpt-4o-mini", re.I), ModelFamily.OPENAI_GPT4_MINI),
    (re.compile(r"gpt-4", re.I), ModelFamily.OPENAI_GPT4),
    (re.compile(r"o1-", re.I), ModelFamily.OPENAI_O1),
    (re.compile(r"o3-", re.I), ModelFamily.OPENAI_O3),
    (re.compile(r"gemini.*flash", re.I), ModelFamily.GEMINI_FLASH),
    (re.compile(r"gemini.*pro|gemini.*ultra", re.I), ModelFamily.GEMINI_PRO),
    (re.compile(r"claude.*haiku", re.I), ModelFamily.CLAUDE_HAIKU),
    (re.compile(r"claude.*sonnet", re.I), ModelFamily.CLAUDE_SONNET),
    (re.compile(r"claude.*opus", re.I), ModelFamily.CLAUDE_OPUS),
    (re.compile(r"llama", re.I), ModelFamily.LLAMA),
    (re.compile(r"mistral|mixtral", re.I), ModelFamily.MISTRAL),
    (re.compile(r"deepseek", re.I), ModelFamily.DEEPSEEK),
]


def resolve_model_family(model_name: str) -> ModelFamily:
    """Resolve a model name string to a ModelFamily.

    Handles version suffixes, date stamps, and common aliases:
    - "gpt-4o-2024-05-13" → OPENAI_GPT4
    - "gemini-2.5-flash" → GEMINI_FLASH
    - "claude-3-5-sonnet-20241022" → CLAUDE_SONNET
    """
    # Check custom profiles first
    if model_name in _custom_profiles:
        return _custom_profiles[model_name].family

    for pattern, family in _MODEL_NAME_PATTERNS:
        if pattern.search(model_name):
            return family

    return ModelFamily.UNKNOWN


def get_profile(model_name: str) -> ModelProfile:
    """Get the behavioral profile for a model.

    Args:
        model_name: Model name string (e.g., "gpt-4o", "gemini-2.5-flash")

    Returns:
        ModelProfile with behavioral baselines for this model
    """
    # Check for exact custom profile
    if model_name in _custom_profiles:
        return _custom_profiles[model_name]

    family = resolve_model_family(model_name)
    return _BUILTIN_PROFILES[family]


def register_profile(model_name: str, profile: ModelProfile) -> None:
    """Register a custom model profile.

    Use this for fine-tuned models, internal models, or new model releases.
    """
    _custom_profiles[model_name] = profile


# Metrics used for statistically corroborated drift alerts
QUALITY_METRICS: tuple[str, ...] = (
    "depth",
    "verification_steps",
    "correction_count",
    "uncertainty_markers",
    "total_steps",
)
LENGTH_METRICS: tuple[str, ...] = ("output_length", "reasoning_length", "compression_ratio")


@dataclass
class AdaptiveThresholds:
    """Thresholds adjusted for a specific model's behavioral profile.

    For alerting, builds per-metric distributions from the user's pinned baseline
    history. Alerts require corroboration across multiple metrics — never a lone
    length change in isolation.
    """

    profile: ModelProfile

    # Adjusted thresholds
    depth_min_scale: float = 1.0
    depth_max_scale: float = 1.0
    step_min_scale: float = 1.0
    step_max_scale: float = 1.0
    verification_scale: float = 1.0

    # Tolerance bands (percentage of typical range)
    tolerance: float = 0.2  # 20% tolerance by default

    def adjust_depth_min(self, contract_min: int) -> int:
        """Adjust a contract's depth minimum for this model."""
        scaled = int(contract_min * self.profile.depth_scale)
        tolerance_band = int(scaled * self.tolerance)
        return max(1, scaled - tolerance_band)

    def adjust_depth_max(self, contract_max: int) -> int:
        """Adjust a contract's depth maximum for this model."""
        scaled = int(contract_max * self.profile.depth_scale)
        tolerance_band = int(scaled * self.tolerance)
        return scaled + tolerance_band

    def adjust_step_min(self, contract_min: int) -> int:
        """Adjust a contract's step minimum for this model."""
        scaled = int(contract_min * self.profile.step_scale)
        tolerance_band = int(scaled * self.tolerance)
        return max(1, scaled - tolerance_band)

    def adjust_step_max(self, contract_max: int) -> int:
        """Adjust a contract's step maximum for this model."""
        scaled = int(contract_max * self.profile.step_scale)
        tolerance_band = int(scaled * self.tolerance)
        return scaled + tolerance_band

    def adjust_verification_min(self, contract_min: int) -> int:
        """Adjust verification step minimum."""
        scaled = int(contract_min * self.profile.verification_scale)
        return max(0, scaled)

    def is_hedging_ratio_normal(self, ratio: float) -> bool:
        """Check if a hedging ratio is within normal range for this model."""
        typical = self.profile.typical_hedging_ratio
        band = typical * self.tolerance * 2  # Double tolerance for hedging
        return (typical - band) <= ratio <= (typical + band + 0.1)

    def build_metric_distribution(
        self,
        fingerprints: list[BehavioralFingerprint],
    ) -> dict[str, tuple[float, float]]:
        """Mean and std-dev per metric from baseline-era history."""
        metrics = list(QUALITY_METRICS) + list(LENGTH_METRICS) + ["hedging_ratio"]
        dist: dict[str, tuple[float, float]] = {}
        for metric in metrics:
            values = [float(getattr(fp, metric)) for fp in fingerprints]
            if not values:
                dist[metric] = (0.0, 1.0)
                continue
            mean = sum(values) / len(values)
            if len(values) > 1:
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                std = math.sqrt(variance)
            else:
                std = max(0.1, abs(mean) * self.tolerance)
            dist[metric] = (mean, max(std, 1e-6))
        return dist

    def metric_z_score(
        self,
        metric: str,
        value: float,
        distribution: dict[str, tuple[float, float]],
    ) -> float:
        mean, std = distribution.get(metric, (value, 1.0))
        return abs(value - mean) / std

    def is_multimetric_outlier(
        self,
        current: BehavioralFingerprint,
        distribution: dict[str, tuple[float, float]],
        z_threshold: float = 2.0,
        min_outlier_metrics: int = 2,
    ) -> tuple[bool, list[dict]]:
        """Return (should_alert, outlier_details).

        Single-metric moves (especially output length alone) never alert.
        At least one quality metric must be an outlier alongside another metric.
        """
        outliers: list[dict] = []
        for metric, (mean, _std) in distribution.items():
            value = float(getattr(current, metric))
            z = self.metric_z_score(metric, value, distribution)
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


def get_adaptive_thresholds(
    model_name: str,
    tolerance: float = 0.2,
) -> AdaptiveThresholds:
    """Get adaptive thresholds for a model.

    Args:
        model_name: Model name string
        tolerance: Tolerance band (0.0 = strict, 0.5 = very lenient)
    """
    profile = get_profile(model_name)
    return AdaptiveThresholds(profile=profile, tolerance=tolerance)


class CalibrationEngine:
    """Learns model profiles from observed behavioral data.

    Feed it fingerprints from a model, and it computes the profile
    automatically. Use for:
    - New/unknown models
    - Fine-tuned models with different behavior
    - Periodic recalibration
    """

    def __init__(self):
        self._observations: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def observe(self, model: str, fingerprint_data: dict) -> None:
        """Record an observation for a model."""
        with self._lock:
            if model not in self._observations:
                self._observations[model] = []
            self._observations[model].append(fingerprint_data)

    def calibrate(self, model: str, min_observations: int = 10) -> Optional[ModelProfile]:
        """Generate a profile from observed data.

        Returns None if insufficient observations.
        """
        with self._lock:
            observations = list(self._observations.get(model, []))
        if len(observations) < min_observations:
            return None

        # Compute statistics
        depths = [o.get("depth", 0) for o in observations]
        corrections = [o.get("correction_count", 0) for o in observations]
        uncertainties = [o.get("uncertainty_markers", 0) for o in observations]
        confidences = [o.get("confidence_markers", 0) for o in observations]
        verifications = [o.get("verification_steps", 0) for o in observations]
        output_lengths = [o.get("output_length", 0) for o in observations]
        reasoning_lengths = [o.get("reasoning_length", 0) for o in observations]
        hedging_ratios = [o.get("hedging_ratio", 0) for o in observations]

        def _mean(vals: list) -> float:
            return sum(vals) / len(vals) if vals else 0

        def _percentile(vals: list, pct: float) -> float:
            if not vals:
                return 0
            sorted_vals = sorted(vals)
            idx = int(len(sorted_vals) * pct)
            return sorted_vals[min(idx, len(sorted_vals) - 1)]

        avg_output = _mean(output_lengths)
        avg_reasoning = _mean(reasoning_lengths)

        # Build profile
        family = resolve_model_family(model)
        profile = ModelProfile(
            family=family,
            display_name=f"Calibrated: {model}",
            typical_depth_min=max(1, int(_percentile(depths, 0.1))),
            typical_depth_max=int(_percentile(depths, 0.9)),
            typical_correction_rate=_mean(corrections) / max(1, avg_output / 1000),
            typical_uncertainty_rate=_mean(uncertainties) / max(1, avg_output / 1000),
            typical_confidence_rate=_mean(confidences) / max(1, avg_output / 1000),
            typical_verification_rate=_mean(verifications) / max(1, avg_output / 1000),
            typical_output_length=int(avg_output),
            typical_reasoning_length=int(avg_reasoning),
            typical_compression_ratio=(
                avg_output / max(1, avg_reasoning) if avg_reasoning > 0 else 1.0
            ),
            typical_hedging_ratio=_mean(hedging_ratios),
            supports_reasoning_tokens=avg_reasoning > 100,
            depth_scale=max(0.5, _mean(depths) / 5),  # Relative to baseline depth=5
            step_scale=max(0.5, _mean(depths) / 5),
            verification_scale=max(0.3, _mean(verifications) / 2),
        )

        return profile

    def calibrate_and_register(
        self, model: str, min_observations: int = 10
    ) -> Optional[ModelProfile]:
        """Calibrate and register the profile globally."""
        profile = self.calibrate(model, min_observations)
        if profile:
            register_profile(model, profile)
        return profile
