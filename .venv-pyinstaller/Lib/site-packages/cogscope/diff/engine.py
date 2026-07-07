"""Semantic diff engine for behavioral fingerprints.

This is the core diffing logic - like git diff but for model behavior.
"""

from datetime import datetime
from typing import Any, Optional

from cogscope.core.exceptions import DiffError
from cogscope.core.models import (
    BehavioralFingerprint,
    BehaviorChange,
    BehaviorDiff,
    ChangeType,
    SignificanceLevel,
)


class DiffEngine:
    """Engine for computing semantic diffs between behavioral fingerprints.

    This is the "git diff" equivalent for model behavior - it identifies
    what changed, how significant the change is, and what it means.
    """

    # Thresholds for change significance
    SIGNIFICANCE_THRESHOLDS = {
        "depth": {"minor": 1, "moderate": 2, "major": 4, "critical": 8},
        "total_steps": {"minor": 2, "moderate": 5, "major": 10, "critical": 20},
        "tool_call_count": {"minor": 1, "moderate": 2, "major": 4, "critical": 6},
        "correction_count": {"minor": 1, "moderate": 2, "major": 3, "critical": 5},
        "uncertainty_markers": {"minor": 2, "moderate": 4, "major": 6, "critical": 10},
        "confidence_markers": {"minor": 2, "moderate": 4, "major": 6, "critical": 10},
        "verification_steps": {"minor": 1, "moderate": 2, "major": 3, "critical": 4},
        "hedging_ratio": {"minor": 0.1, "moderate": 0.2, "major": 0.3, "critical": 0.4},
        "output_length": {"minor": 200, "moderate": 500, "major": 1000, "critical": 2000},
        "tool_diversity": {"minor": 0.1, "moderate": 0.2, "major": 0.3, "critical": 0.4},
    }

    # Weights for drift score calculation
    DRIFT_WEIGHTS = {
        "depth": 1.5,
        "total_steps": 1.2,
        "tool_call_count": 1.3,
        "tool_sequence_changed": 2.0,
        "correction_count": 1.8,
        "verification_steps": 1.6,
        "hedging_ratio": 1.4,
        "structured_output": 1.5,
    }

    def __init__(self):
        pass

    def diff(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> BehaviorDiff:
        """Compute a semantic diff between two fingerprints.

        Args:
            baseline: The baseline behavior to compare against
            current: The current behavior

        Returns:
            A BehaviorDiff showing all changes
        """
        try:
            changes: list[BehaviorChange] = []

            # Compare structural metrics
            changes.extend(self._compare_structural(baseline, current))

            # Compare tool usage
            changes.extend(self._compare_tool_usage(baseline, current))

            # Compare verbosity
            changes.extend(self._compare_verbosity(baseline, current))

            # Compare self-correction
            changes.extend(self._compare_self_correction(baseline, current))

            # Compare uncertainty
            changes.extend(self._compare_uncertainty(baseline, current))

            # Compare quality signals
            changes.extend(self._compare_quality(baseline, current))

            # Calculate overall drift score
            drift_score = self._calculate_drift_score(changes)

            # Determine overall significance
            significance = self._determine_overall_significance(changes, drift_score)

            # Count breaking changes
            breaking_changes = sum(
                1
                for c in changes
                if c.significance in [SignificanceLevel.MAJOR, SignificanceLevel.CRITICAL]
            )

            # Generate summary
            summary = self._generate_summary(changes, drift_score)

            # Generate recommendations
            recommendations = self._generate_recommendations(changes)

            return BehaviorDiff(
                baseline_id=baseline.trace_id,
                current_id=current.trace_id,
                baseline_task_id=baseline.task_id,
                current_task_id=current.task_id,
                timestamp=datetime.utcnow(),
                changes=changes,
                drift_score=drift_score,
                significance=significance,
                total_changes=len([c for c in changes if c.change_type != ChangeType.UNCHANGED]),
                breaking_changes=breaking_changes,
                summary=summary,
                recommendations=recommendations,
            )

        except Exception as e:
            raise DiffError(f"Failed to compute diff: {e}")

    def _compare_structural(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare structural metrics."""
        changes = []

        # Depth
        depth_change = self._create_change(
            "depth", baseline.depth, current.depth, is_percentage=False
        )
        if depth_change:
            changes.append(depth_change)

        # Total steps
        steps_change = self._create_change(
            "total_steps", baseline.total_steps, current.total_steps, is_percentage=False
        )
        if steps_change:
            changes.append(steps_change)

        # Branching factor
        branching_change = self._create_change(
            "branching_factor",
            baseline.branching_factor,
            current.branching_factor,
            is_percentage=True,
        )
        if branching_change:
            changes.append(branching_change)

        return changes

    def _compare_tool_usage(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare tool usage patterns."""
        changes = []

        # Tool call count
        count_change = self._create_change(
            "tool_call_count",
            baseline.tool_call_count,
            current.tool_call_count,
            is_percentage=False,
        )
        if count_change:
            changes.append(count_change)

        # Tool diversity
        diversity_change = self._create_change(
            "tool_diversity", baseline.tool_diversity, current.tool_diversity, is_percentage=True
        )
        if diversity_change:
            changes.append(diversity_change)

        # Tool sequence
        if baseline.tool_call_sequence != current.tool_call_sequence:
            baseline_set = set(baseline.tool_call_sequence)
            current_set = set(current.tool_call_sequence)

            added = current_set - baseline_set
            removed = baseline_set - current_set

            if added or removed:
                desc = []
                if added:
                    desc.append(f"Added tools: {', '.join(added)}")
                if removed:
                    desc.append(f"Removed tools: {', '.join(removed)}")

                changes.append(
                    BehaviorChange(
                        metric="tool_call_sequence",
                        baseline_value=baseline.tool_call_sequence,
                        current_value=current.tool_call_sequence,
                        change_type=ChangeType.CHANGED,
                        magnitude=len(added) + len(removed),
                        significance=self._determine_significance(
                            "tool_call_count", len(added) + len(removed)
                        ),
                        description="; ".join(desc),
                    )
                )

        return changes

    def _compare_verbosity(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare verbosity metrics."""
        changes = []

        # Output length
        length_change = self._create_change(
            "output_length", baseline.output_length, current.output_length, is_percentage=False
        )
        if length_change:
            changes.append(length_change)

        # Compression ratio
        compression_change = self._create_change(
            "compression_ratio",
            baseline.compression_ratio,
            current.compression_ratio,
            is_percentage=True,
        )
        if compression_change:
            changes.append(compression_change)

        return changes

    def _compare_self_correction(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare self-correction patterns."""
        changes = []

        # Correction count
        correction_change = self._create_change(
            "correction_count",
            baseline.correction_count,
            current.correction_count,
            is_percentage=False,
        )
        if correction_change:
            changes.append(correction_change)

        # Backtrack count
        backtrack_change = self._create_change(
            "backtrack_count",
            baseline.backtrack_count,
            current.backtrack_count,
            is_percentage=False,
        )
        if backtrack_change:
            changes.append(backtrack_change)

        return changes

    def _compare_uncertainty(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare uncertainty indicators."""
        changes = []

        # Uncertainty markers
        uncertainty_change = self._create_change(
            "uncertainty_markers",
            baseline.uncertainty_markers,
            current.uncertainty_markers,
            is_percentage=False,
        )
        if uncertainty_change:
            changes.append(uncertainty_change)

        # Confidence markers
        confidence_change = self._create_change(
            "confidence_markers",
            baseline.confidence_markers,
            current.confidence_markers,
            is_percentage=False,
        )
        if confidence_change:
            changes.append(confidence_change)

        # Hedging ratio
        hedging_change = self._create_change(
            "hedging_ratio", baseline.hedging_ratio, current.hedging_ratio, is_percentage=True
        )
        if hedging_change:
            changes.append(hedging_change)

        return changes

    def _compare_quality(
        self,
        baseline: BehavioralFingerprint,
        current: BehavioralFingerprint,
    ) -> list[BehaviorChange]:
        """Compare quality signals."""
        changes = []

        # Verification steps
        verification_change = self._create_change(
            "verification_steps",
            baseline.verification_steps,
            current.verification_steps,
            is_percentage=False,
        )
        if verification_change:
            changes.append(verification_change)

        # Structured output
        if baseline.structured_output != current.structured_output:
            changes.append(
                BehaviorChange(
                    metric="structured_output",
                    baseline_value=baseline.structured_output,
                    current_value=current.structured_output,
                    change_type=(
                        ChangeType.ADDED if current.structured_output else ChangeType.REMOVED
                    ),
                    magnitude=1.0,
                    significance=SignificanceLevel.MODERATE,
                    description=f"Structured output {'added' if current.structured_output else 'removed'}",
                )
            )

        return changes

    def _create_change(
        self,
        metric: str,
        baseline_value: Any,
        current_value: Any,
        is_percentage: bool = False,
    ) -> Optional[BehaviorChange]:
        """Create a BehaviorChange if values differ."""
        if baseline_value == current_value:
            return None

        # Calculate magnitude
        if is_percentage:
            magnitude = abs(current_value - baseline_value)
        else:
            if baseline_value == 0:
                magnitude = abs(current_value)
            else:
                magnitude = abs(current_value - baseline_value)

        # Skip tiny changes
        if magnitude < 0.001:
            return None

        # Determine change type
        if isinstance(baseline_value, (int, float)) and isinstance(current_value, (int, float)):
            if current_value > baseline_value:
                change_type = ChangeType.INCREASED
            else:
                change_type = ChangeType.DECREASED
        else:
            change_type = ChangeType.CHANGED

        # Determine significance
        significance = self._determine_significance(metric, magnitude)

        # Generate description
        if is_percentage:
            desc = f"{metric}: {baseline_value:.2f} → {current_value:.2f} ({magnitude * 100:+.1f}%)"
        else:
            desc = f"{metric}: {baseline_value} → {current_value} ({current_value - baseline_value:+g})"

        return BehaviorChange(
            metric=metric,
            baseline_value=baseline_value,
            current_value=current_value,
            change_type=change_type,
            magnitude=magnitude,
            significance=significance,
            description=desc,
        )

    def _determine_significance(self, metric: str, magnitude: float) -> SignificanceLevel:
        """Determine significance level based on metric and magnitude."""
        thresholds = self.SIGNIFICANCE_THRESHOLDS.get(
            metric, {"minor": 1, "moderate": 2, "major": 4, "critical": 8}
        )

        if magnitude >= thresholds["critical"]:
            return SignificanceLevel.CRITICAL
        elif magnitude >= thresholds["major"]:
            return SignificanceLevel.MAJOR
        elif magnitude >= thresholds["moderate"]:
            return SignificanceLevel.MODERATE
        elif magnitude >= thresholds["minor"]:
            return SignificanceLevel.MINOR
        else:
            return SignificanceLevel.NONE

    def _calculate_drift_score(self, changes: list[BehaviorChange]) -> float:
        """Calculate overall drift score from changes.

        Returns a value between 0 (no drift) and 1 (maximum drift).
        """
        if not changes:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        significance_values = {
            SignificanceLevel.NONE: 0.0,
            SignificanceLevel.MINOR: 0.2,
            SignificanceLevel.MODERATE: 0.5,
            SignificanceLevel.MAJOR: 0.8,
            SignificanceLevel.CRITICAL: 1.0,
        }

        for change in changes:
            weight = self.DRIFT_WEIGHTS.get(change.metric, 1.0)
            sig_value = significance_values[change.significance]
            weighted_sum += weight * sig_value
            total_weight += weight

        if total_weight == 0:
            return 0.0

        # Normalize to 0-1
        raw_score = weighted_sum / total_weight

        # Apply non-linear scaling for better sensitivity
        drift_score = min(1.0, raw_score * 1.5)

        return round(drift_score, 3)

    def _determine_overall_significance(
        self,
        changes: list[BehaviorChange],
        drift_score: float,
    ) -> SignificanceLevel:
        """Determine overall significance level."""
        if drift_score >= 0.8:
            return SignificanceLevel.CRITICAL
        elif drift_score >= 0.5:
            return SignificanceLevel.MAJOR
        elif drift_score >= 0.3:
            return SignificanceLevel.MODERATE
        elif drift_score >= 0.1:
            return SignificanceLevel.MINOR
        else:
            return SignificanceLevel.NONE

    def _generate_summary(self, changes: list[BehaviorChange], drift_score: float) -> str:
        """Generate a human-readable summary of changes."""
        if not changes:
            return "No behavioral changes detected."

        active_changes = [c for c in changes if c.change_type != ChangeType.UNCHANGED]

        if not active_changes:
            return "No significant behavioral changes."

        parts = []

        # Count by significance
        critical = sum(1 for c in active_changes if c.significance == SignificanceLevel.CRITICAL)
        major = sum(1 for c in active_changes if c.significance == SignificanceLevel.MAJOR)
        moderate = sum(1 for c in active_changes if c.significance == SignificanceLevel.MODERATE)

        if critical > 0:
            parts.append(f"{critical} critical change(s)")
        if major > 0:
            parts.append(f"{major} major change(s)")
        if moderate > 0:
            parts.append(f"{moderate} moderate change(s)")

        summary = f"Drift score: {drift_score:.1%}. "
        if parts:
            summary += "Detected " + ", ".join(parts) + "."

        return summary

    def _generate_recommendations(self, changes: list[BehaviorChange]) -> list[str]:
        """Generate actionable recommendations based on changes."""
        recommendations = []

        for change in changes:
            if change.significance not in [SignificanceLevel.MAJOR, SignificanceLevel.CRITICAL]:
                continue

            if change.metric == "verification_steps" and change.change_type == ChangeType.DECREASED:
                recommendations.append(
                    "⚠️ Verification steps decreased - model may be less thorough in checking its work"
                )
            elif change.metric == "correction_count" and change.change_type == ChangeType.DECREASED:
                recommendations.append(
                    "⚠️ Self-correction decreased - model may be too confident in initial answers"
                )
            elif change.metric == "depth" and change.change_type == ChangeType.DECREASED:
                recommendations.append(
                    "⚠️ Reasoning depth decreased - model is thinking less deeply"
                )
            elif change.metric == "tool_call_sequence":
                recommendations.append(
                    "🔧 Tool usage pattern changed - review tool calls for correctness"
                )
            elif change.metric == "hedging_ratio" and change.change_type == ChangeType.INCREASED:
                recommendations.append(
                    "❓ Uncertainty increased significantly - model may be less reliable"
                )

        if not recommendations:
            recommendations.append("✅ No critical issues detected - review changes for context")

        return recommendations
