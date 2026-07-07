"""Drift detector for Cogscope.

DESIGN PRINCIPLE (alerting): An alert fires only when multiple behavioral metrics
deviate significantly from the pinned baseline's own historical distribution for
that task and model. Live proxy traffic uses KSWIN/MDDM streaming detectors per
metric (see streaming.py). Batch diff/check uses Mann-Whitney with
Benjamini-Hochberg FDR and the Cauchy Combination Test (see batch.py). Never
alert on a single metric in isolation, especially not output length alone.

Structural drift (heuristic fingerprint shifts) does not prove quality regression.
It means something changed; investigate before assuming the model got worse.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from cogscope.core.config import get_config
from cogscope.core.exceptions import DriftError
from cogscope.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorChange,
    ChangeType,
    DriftReport,
    SignificanceLevel,
)
from cogscope.diff.engine import DiffEngine
from cogscope.drift.scoring import DriftScorer
from cogscope.storage.database import Database, get_database


@dataclass
class DriftAssessment:
    """Result of assessing one fingerprint against a pinned baseline."""

    should_alert: bool
    drift_score: float
    baseline_name: Optional[str]
    outliers: list[dict] = field(default_factory=list)
    summary: str = ""
    plain_language: list[str] = field(default_factory=list)
    structural_alert: bool = False
    semantic_alert: bool = False


class DriftDetector:
    """Detect behavioral drift over time.

    Monitors reasoning behavior for:
    - Silent regressions
    - Reasoning shape changes
    - Confidence vs correctness divergence
    - Statistical anomalies
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        window_size: int = 100,
        significance_threshold: float = 0.05,
    ):
        self.db = db or get_database()
        self.scorer = DriftScorer()
        self.diff_engine = DiffEngine()
        self.window_size = window_size
        self.significance_threshold = significance_threshold

    def detect_drift(
        self,
        task_id: str,
        baseline_name: Optional[str] = None,
        window_hours: int = 24,
    ) -> DriftReport:
        """Detect drift for a task compared to baseline.

        Args:
            task_id: The task to analyze
            baseline_name: Optional baseline to compare against
            window_hours: Time window for recent traces

        Returns:
            DriftReport with analysis results
        """
        try:
            # Get recent fingerprints
            recent_fps = self.db.get_fingerprints_by_task(task_id, limit=self.window_size)

            if len(recent_fps) < 3:
                return self._empty_report(task_id, "Insufficient data")

            # Filter by time window
            cutoff = datetime.utcnow() - timedelta(hours=window_hours)
            recent_fps = [fp for fp in recent_fps if fp.timestamp >= cutoff]

            if len(recent_fps) < 3:
                return self._empty_report(task_id, "Insufficient recent data")

            # Get baseline
            baseline_fp = None
            baseline_id = None

            if baseline_name:
                try:
                    baseline = self.db.get_baseline(baseline_name)
                    baseline_fp = self.db.get_fingerprint(baseline.fingerprint_id)
                    baseline_id = baseline.id
                except Exception:
                    pass

            # If no baseline, use oldest fingerprints as reference
            if baseline_fp is None:
                historical_fps = self.db.get_fingerprints_by_task(task_id, limit=200)
                if len(historical_fps) > 20:
                    # Use oldest 20% as baseline population
                    baseline_count = max(5, len(historical_fps) // 5)
                    baseline_fps = historical_fps[-baseline_count:]
                else:
                    baseline_fps = recent_fps[: len(recent_fps) // 2]

            # Calculate drift scores
            if baseline_fp:
                # Single baseline comparison
                drift_scores, significant_changes = self._compare_to_baseline(
                    baseline_fp, recent_fps
                )
            else:
                # Population comparison
                drift_scores, significant_changes = self._compare_populations(
                    baseline_fps, recent_fps
                )

            # Calculate aggregate score
            aggregate_drift = self.scorer.compute_aggregate_drift(drift_scores)

            # Detect trend
            trend_info = self._detect_trend(recent_fps)

            # Calculate variance
            variance, std_dev = self._calculate_variance(recent_fps)

            return DriftReport(
                id=f"drift_{uuid.uuid4().hex[:8]}",
                task_id=task_id,
                baseline_id=baseline_id,
                start_time=cutoff,
                end_time=datetime.utcnow(),
                drift_score=aggregate_drift,
                drift_trend=trend_info["direction"],
                significant_changes=significant_changes,
                sample_count=len(recent_fps),
                variance=variance,
                std_deviation=std_dev,
                z_scores=drift_scores,
                summary=self._generate_summary(aggregate_drift, trend_info, significant_changes),
            )

        except Exception as e:
            raise DriftError(f"Failed to detect drift: {e}")

    def _compare_to_baseline(
        self,
        baseline: BehavioralFingerprint,
        recent: list[BehavioralFingerprint],
    ) -> tuple[dict[str, float], list[BehaviorChange]]:
        """Compare recent fingerprints to a single baseline."""
        drift_scores = {}
        significant_changes = []

        # Metrics to analyze
        metrics = [
            ("depth", "depth"),
            ("total_steps", "steps"),
            ("tool_call_count", "tools"),
            ("correction_count", "corrections"),
            ("uncertainty_markers", "uncertainty"),
            ("verification_steps", "verification"),
            ("hedging_ratio", "hedging"),
        ]

        for attr, name in metrics:
            baseline_val = getattr(baseline, attr)
            recent_vals = [getattr(fp, attr) for fp in recent]

            # Calculate mean of recent
            recent_mean = sum(recent_vals) / len(recent_vals)

            # Z-score of recent mean vs baseline
            if len(recent_vals) > 1:
                recent_std = (
                    sum((v - recent_mean) ** 2 for v in recent_vals) / len(recent_vals)
                ) ** 0.5
                if recent_std > 0:
                    z = abs(recent_mean - baseline_val) / recent_std
                    p = 1 - min(0.999, 2 * (1 - 0.5 * (1 + (z / (1 + z)))))  # Approximate
                else:
                    z = 0
                    p = 1
            else:
                z = abs(recent_mean - baseline_val)
                p = 1

            drift_scores[attr] = 1 - p

            # Check for significant change
            if p < self.significance_threshold:
                change_type = (
                    ChangeType.INCREASED if recent_mean > baseline_val else ChangeType.DECREASED
                )
                significance = self._score_to_significance(1 - p)

                significant_changes.append(
                    BehaviorChange(
                        metric=attr,
                        baseline_value=baseline_val,
                        current_value=recent_mean,
                        change_type=change_type,
                        magnitude=abs(recent_mean - baseline_val),
                        significance=significance,
                        description=f"{name}: {baseline_val:.2f} → {recent_mean:.2f}",
                    )
                )

        return drift_scores, significant_changes

    def _compare_populations(
        self,
        baseline_fps: list[BehavioralFingerprint],
        recent_fps: list[BehavioralFingerprint],
    ) -> tuple[dict[str, float], list[BehaviorChange]]:
        """Compare two populations using Mann-Whitney + BH + CCT."""
        from cogscope.drift.batch import batch_drift_test, outliers_from_batch

        batch = batch_drift_test(baseline_fps, recent_fps, alpha=self.significance_threshold)
        significant_changes = []

        for o in outliers_from_batch(batch):
            change_type = (
                ChangeType.INCREASED
                if o["current_value"] > o["baseline_mean"]
                else ChangeType.DECREASED
            )
            significance = self._score_to_significance(1 - o["p_value"])
            significant_changes.append(
                BehaviorChange(
                    metric=o["metric"],
                    baseline_value=o["baseline_mean"],
                    current_value=o["current_value"],
                    change_type=change_type,
                    magnitude=abs(o["current_value"] - o["baseline_mean"]),
                    significance=significance,
                    description=(
                        f"{o['metric']}: {o['baseline_mean']:.2f} → "
                        f"{o['current_value']:.2f} (BH rejected)"
                    ),
                )
            )

        drift_scores = {m.metric: 1 - m.p_value for m in batch.metric_results}
        if batch.should_alert:
            drift_scores["cct_omnibus"] = 1 - batch.cct_p_value

        return drift_scores, significant_changes

    def _detect_trend(self, fingerprints: list[BehavioralFingerprint]) -> dict:
        """Detect trend in fingerprints over time."""
        if len(fingerprints) < 5:
            return {"direction": "stable", "slope": 0, "significance": 0}

        # Use depth as primary trend indicator
        values = [fp.depth for fp in sorted(fingerprints, key=lambda x: x.timestamp)]
        return self.scorer.trend_detection(values)

    def _calculate_variance(
        self,
        fingerprints: list[BehavioralFingerprint],
    ) -> tuple[float, float]:
        """Calculate variance and std deviation of key metrics."""
        if len(fingerprints) < 2:
            return 0.0, 0.0

        # Combine normalized scores
        variances = []
        for attr in ["depth", "correction_count", "hedging_ratio"]:
            values = [getattr(fp, attr) for fp in fingerprints]
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            variances.append(var)

        avg_variance = sum(variances) / len(variances)
        std_dev = avg_variance**0.5

        return avg_variance, std_dev

    def _score_to_significance(self, score: float) -> SignificanceLevel:
        """Convert drift score to significance level."""
        if score >= 0.95:
            return SignificanceLevel.CRITICAL
        elif score >= 0.9:
            return SignificanceLevel.MAJOR
        elif score >= 0.8:
            return SignificanceLevel.MODERATE
        elif score >= 0.5:
            return SignificanceLevel.MINOR
        else:
            return SignificanceLevel.NONE

    def _generate_summary(
        self,
        drift_score: float,
        trend: dict,
        changes: list[BehaviorChange],
    ) -> str:
        """Generate human-readable summary."""
        parts = [f"Drift score: {drift_score:.1%}"]

        if trend["direction"] != "stable":
            parts.append(f"Trend: {trend['direction']}")

        if changes:
            critical = sum(1 for c in changes if c.significance == SignificanceLevel.CRITICAL)
            major = sum(1 for c in changes if c.significance == SignificanceLevel.MAJOR)

            if critical:
                parts.append(f"{critical} critical changes")
            if major:
                parts.append(f"{major} major changes")

        return ". ".join(parts) + "."

    def _empty_report(self, task_id: str, reason: str) -> DriftReport:
        """Create an empty report when analysis isn't possible."""
        return DriftReport(
            id=f"drift_{uuid.uuid4().hex[:8]}",
            task_id=task_id,
            baseline_id=None,
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow(),
            drift_score=0.0,
            drift_trend="stable",
            significant_changes=[],
            sample_count=0,
            variance=0.0,
            std_deviation=0.0,
            z_scores={},
            summary=reason,
        )

    def quick_check(
        self,
        current: BehavioralFingerprint,
        baseline: BehavioralFingerprint,
    ) -> tuple[float, str]:
        """Quick drift check between two fingerprints.

        Returns:
            (drift_score, status_message)
        """
        diff = self.diff_engine.diff(baseline, current)

        if diff.drift_score < 0.1:
            status = "✅ Behavior stable"
        elif diff.drift_score < 0.3:
            status = "ℹ️ Minor changes detected"
        elif diff.drift_score < 0.5:
            status = "⚠️ Moderate drift detected"
        else:
            status = "🚨 Significant drift detected"

        return diff.drift_score, status

    def assess_against_pinned_baseline(
        self,
        current: BehavioralFingerprint,
        baseline_fp: BehavioralFingerprint,
        historical: list[BehavioralFingerprint],
        baseline_name: Optional[str] = None,
        model_name: Optional[str] = None,
        semantic_text: Optional[str] = None,
        semantic_analyzer=None,
    ) -> DriftAssessment:
        """Assess one live capture using KSWIN/MDDM streaming detectors.

        Maintains per-(model, baseline) streaming state; structural drift alerts
        require corroboration across multiple metric streams.
        """
        from cogscope.drift.streaming import get_streaming_registry

        model = model_name or current.model
        bname = baseline_name or "default"

        population = list(historical) if historical else [baseline_fp]
        pop_ids = {fp.trace_id for fp in population}
        if baseline_fp.trace_id not in pop_ids:
            population = [baseline_fp, *population]

        registry = get_streaming_registry()
        monitor = registry.get_or_create(model, bname)
        if not monitor._seeded:
            monitor.seed_from_history(population)

        drift_flags = monitor.update(current)
        structural_alert, outliers = monitor.combine_streaming_signals(drift_flags)

        semantic_alert = False
        semantic_note = None
        if semantic_analyzer is not None and semantic_text:
            sem = semantic_analyzer.compare_current_text(semantic_text)
            semantic_note = sem.summary
            if sem.drift_detected:
                semantic_alert = True
                outliers = list(outliers) + [
                    {
                        "metric": "semantic_embedding",
                        "streaming_drift": True,
                        "is_quality": False,
                        "is_length": False,
                        "direction": "semantic shift",
                        "drift_type": "semantic",
                        "js_distance": sem.distance,
                    }
                ]

        should_alert = structural_alert or semantic_alert

        diff = self.diff_engine.diff(baseline_fp, current)
        drift_score = diff.drift_score

        plain: list[str] = []
        for o in outliers:
            metric = o["metric"].replace("_", " ")
            drift_type = o.get("drift_type", "structural")
            if drift_type == "semantic":
                plain.append(f"Semantic drift: {metric} ({o.get('direction', 'shift')})")
            elif "baseline_mean" in o:
                plain.append(
                    f"Structural drift: {metric} {o['direction']} from typical "
                    f"{o['baseline_mean']:.1f} to {o['current_value']:.1f}"
                )
            else:
                detector_name = o.get("detector", "kswin/mddm")
                plain.append(f"Structural drift: {metric} ({detector_name})")

        if not should_alert and outliers:
            summary = "Within baseline statistical range (no corroborated drift)."
        elif should_alert:
            kinds = []
            if structural_alert:
                kinds.append("structural")
            if semantic_alert:
                kinds.append("semantic")
            summary = (
                f"{' + '.join(kinds).title()} drift across {len(outliers)} signal(s). "
                "Structural shifts often reflect provider tuning, not capability loss. "
                "Investigate before assuming regression."
            )
        else:
            summary = "Behavior matches pinned baseline distribution."

        if semantic_note:
            summary = f"{summary} {semantic_note}"

        return DriftAssessment(
            should_alert=should_alert,
            drift_score=drift_score,
            baseline_name=baseline_name,
            outliers=outliers,
            summary=summary,
            plain_language=plain,
            structural_alert=structural_alert,
            semantic_alert=semantic_alert,
        )
