"""Fingerprint normalization and hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from cogscope.core.models import BehavioralFingerprint


class FingerprintNormalizer:
    """Normalize fingerprints for consistent comparison.

    Normalization ensures that fingerprints from different contexts
    can be meaningfully compared.
    """

    # Default weights for signature generation
    DEFAULT_WEIGHTS = {
        "depth": 1.0,
        "branching_factor": 0.8,
        "total_steps": 1.0,
        "tool_call_count": 0.9,
        "correction_count": 1.2,  # Corrections are significant
        "uncertainty_markers": 0.8,
        "verification_steps": 1.1,
        "hedging_ratio": 0.9,
    }

    # Normalization ranges (min, max) for each metric
    NORMALIZATION_RANGES = {
        "depth": (1, 20),
        "branching_factor": (0, 2),
        "total_steps": (1, 50),
        "tool_call_count": (0, 20),
        "tool_diversity": (0, 1),
        "output_length": (0, 10000),
        "reasoning_length": (0, 50000),
        "compression_ratio": (0, 5),
        "correction_count": (0, 10),
        "uncertainty_markers": (0, 20),
        "confidence_markers": (0, 20),
        "hedging_ratio": (0, 1),
        "verification_steps": (0, 5),
        "tokens_per_step": (0, 1000),
        "reasoning_overhead": (0, 10),
    }

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def normalize_value(self, metric: str, value: float) -> float:
        """Normalize a single metric value to [0, 1] range."""
        if metric not in self.NORMALIZATION_RANGES:
            return value

        min_val, max_val = self.NORMALIZATION_RANGES[metric]
        normalized = (value - min_val) / (max_val - min_val)
        return max(0.0, min(1.0, normalized))

    def normalize_fingerprint(self, fp: BehavioralFingerprint) -> dict[str, float]:
        """Normalize all fingerprint metrics."""
        return {
            "depth": self.normalize_value("depth", fp.depth),
            "branching_factor": self.normalize_value("branching_factor", fp.branching_factor),
            "total_steps": self.normalize_value("total_steps", fp.total_steps),
            "tool_call_count": self.normalize_value("tool_call_count", fp.tool_call_count),
            "tool_diversity": fp.tool_diversity,  # Already 0-1
            "output_length": self.normalize_value("output_length", fp.output_length),
            "reasoning_length": self.normalize_value("reasoning_length", fp.reasoning_length),
            "compression_ratio": self.normalize_value("compression_ratio", fp.compression_ratio),
            "correction_count": self.normalize_value("correction_count", fp.correction_count),
            "uncertainty_markers": self.normalize_value(
                "uncertainty_markers", fp.uncertainty_markers
            ),
            "confidence_markers": self.normalize_value("confidence_markers", fp.confidence_markers),
            "hedging_ratio": fp.hedging_ratio,  # Already 0-1
            "verification_steps": self.normalize_value("verification_steps", fp.verification_steps),
            "tokens_per_step": self.normalize_value("tokens_per_step", fp.tokens_per_step),
            "reasoning_overhead": self.normalize_value("reasoning_overhead", fp.reasoning_overhead),
        }

    def compute_signature_hash(self, fp: BehavioralFingerprint) -> str:
        """Compute a normalized signature hash for quick comparison.

        The hash represents the "behavioral signature" - a compact
        representation that groups similar reasoning patterns together.
        """
        # Extract key behavioral indicators
        signature_data = {
            # Structural
            "depth_bucket": self._bucket_value(fp.depth, [2, 5, 10, 20]),
            "steps_bucket": self._bucket_value(fp.total_steps, [3, 10, 20, 50]),
            # Tool usage
            "uses_tools": fp.tool_call_count > 0,
            "tool_count_bucket": self._bucket_value(fp.tool_call_count, [1, 3, 5, 10]),
            "tool_sequence_prefix": tuple(fp.tool_call_sequence[:3]),
            # Reasoning style
            "has_corrections": fp.correction_count > 0,
            "uncertainty_level": self._bucket_value(fp.hedging_ratio, [0.2, 0.4, 0.6, 0.8]),
            "has_verification": fp.verification_steps > 0,
            # Output style
            "structured": fp.structured_output,
            "verbosity_bucket": self._bucket_value(fp.output_length, [500, 1500, 3000, 6000]),
        }

        # Create stable JSON representation
        content = json.dumps(signature_data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _bucket_value(self, value: float, thresholds: list[float]) -> int:
        """Bucket a value into discrete ranges."""
        for i, threshold in enumerate(thresholds):
            if value <= threshold:
                return i
        return len(thresholds)

    def compute_similarity(
        self,
        fp1: BehavioralFingerprint,
        fp2: BehavioralFingerprint,
    ) -> float:
        """Compute similarity score between two fingerprints.

        Returns a value between 0 (completely different) and 1 (identical).
        """
        # Get normalized vectors
        norm1 = self.normalize_fingerprint(fp1)
        norm2 = self.normalize_fingerprint(fp2)

        # Compute weighted euclidean distance
        total_weight = 0.0
        weighted_diff_sq = 0.0

        for metric in norm1:
            weight = self.weights.get(metric, 1.0)
            diff = norm1[metric] - norm2[metric]
            weighted_diff_sq += weight * (diff**2)
            total_weight += weight

        # Normalize distance
        avg_dist = (weighted_diff_sq / total_weight) ** 0.5

        # Convert distance to similarity
        similarity = 1.0 / (1.0 + avg_dist * 3)

        return similarity

    def to_vector(self, fp: BehavioralFingerprint) -> np.ndarray:
        """Convert fingerprint to numpy vector for ML operations."""
        return np.array(fp.to_vector())

    def cosine_similarity(
        self,
        fp1: BehavioralFingerprint,
        fp2: BehavioralFingerprint,
    ) -> float:
        """Compute cosine similarity between fingerprint vectors."""
        v1 = self.to_vector(fp1)
        v2 = self.to_vector(fp2)

        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
