"""Baseline management for known-good behaviors."""

import uuid
from datetime import datetime
from typing import Optional

from cogscope.core.exceptions import BaselineNotFoundError
from cogscope.core.models import Baseline, BehavioralFingerprint, ReasoningTrace
from cogscope.storage.database import Database, get_database


class BaselineManager:
    """Manage baselines (known-good behaviors).

    A baseline is a pinned snapshot of expected/desired behavior
    that new traces can be compared against.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def create(
        self,
        trace_id: str,
        name: str,
        description: Optional[str] = None,
    ) -> Baseline:
        """Create a baseline from an existing trace.

        Args:
            trace_id: ID of the trace to use as baseline
            name: Unique name for the baseline
            description: Optional description

        Returns:
            Created Baseline
        """
        # Get trace and fingerprint
        trace = self.db.get_trace(trace_id)
        fp = self.db.get_fingerprint_by_trace(trace_id)

        if not fp:
            # Generate fingerprint if not exists
            from cogscope.fingerprint.extractor import FingerprintExtractor

            extractor = FingerprintExtractor()
            fp = extractor.extract(trace)
            self.db.save_fingerprint(fp)

        baseline = Baseline(
            id=f"baseline_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            task_id=trace.task_id,
            fingerprint_id=f"fp_{trace_id}",
            trace_id=trace_id,
            created_at=datetime.utcnow(),
        )

        self.db.save_baseline(baseline)
        return baseline

    def create_from_fingerprint(
        self,
        fingerprint: BehavioralFingerprint,
        name: str,
        description: Optional[str] = None,
    ) -> Baseline:
        """Create a baseline from a fingerprint directly."""
        self.db.save_fingerprint(fingerprint)

        baseline = Baseline(
            id=f"baseline_{uuid.uuid4().hex[:8]}",
            name=name,
            description=description,
            task_id=fingerprint.task_id,
            fingerprint_id=f"fp_{fingerprint.trace_id}",
            trace_id=fingerprint.trace_id,
            created_at=datetime.utcnow(),
        )

        self.db.save_baseline(baseline)
        return baseline

    def get(self, name: str) -> Baseline:
        """Get a baseline by name."""
        return self.db.get_baseline(name)

    def list(self, task_id: Optional[str] = None) -> list[Baseline]:
        """List baselines, optionally filtered by task."""
        if task_id:
            return self.db.get_baselines_for_task(task_id)
        return self.db.list_baselines()

    def deactivate(self, name: str) -> None:
        """Deactivate a baseline (soft delete)."""
        baseline = self.db.get_baseline(name)
        baseline.is_active = False
        self.db.save_baseline(baseline)

    def get_fingerprint(self, name: str) -> BehavioralFingerprint:
        """Get the fingerprint for a baseline."""
        baseline = self.db.get_baseline(name)
        return self.db.get_fingerprint(baseline.fingerprint_id)

    def compare_to_current(
        self,
        baseline_name: str,
        current_trace_id: str,
    ) -> dict:
        """Compare a baseline to a current trace."""
        from cogscope.diff.engine import DiffEngine

        _baseline = self.get(baseline_name)
        baseline_fp = self.get_fingerprint(baseline_name)
        current_fp = self.db.get_fingerprint_by_trace(current_trace_id)

        if not current_fp:
            raise ValueError(f"No fingerprint found for trace: {current_trace_id}")

        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        return {
            "baseline": baseline_name,
            "current_trace": current_trace_id,
            "drift_score": diff.drift_score,
            "significance": diff.significance.value,
            "changes_count": diff.total_changes,
            "breaking_changes": diff.breaking_changes,
            "summary": diff.summary,
        }
