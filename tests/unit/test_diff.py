"""Unit tests for diff engine."""

import pytest

from cogscope.core.models import (
    BehavioralFingerprint,
    BehaviorChange,
    BehaviorDiff,
    ChangeType,
    SignificanceLevel,
)
from cogscope.diff.engine import DiffEngine
from cogscope.diff.formatter import DiffFormatter


class TestDiffEngine:
    """Tests for DiffEngine."""

    @pytest.fixture
    def baseline_fp(self):
        """Create baseline fingerprint."""
        return BehavioralFingerprint(
            trace_id="baseline_trace",
            task_id="test_task",
            depth=5,
            branching_factor=0.5,
            total_steps=5,
            tool_call_count=2,
            tool_call_sequence=["search", "calculate"],
            tool_diversity=1.0,
            correction_count=1,
            uncertainty_markers=2,
            confidence_markers=3,
            hedging_ratio=0.4,
            verification_steps=2,
            output_length=500,
            structured_output=False,
        )

    @pytest.fixture
    def current_fp(self):
        """Create current fingerprint (with changes)."""
        return BehavioralFingerprint(
            trace_id="current_trace",
            task_id="test_task",
            depth=3,  # Decreased
            branching_factor=0.3,
            total_steps=3,  # Decreased
            tool_call_count=4,  # Increased
            tool_call_sequence=["search", "calculate", "analyze"],  # Changed
            tool_diversity=0.75,
            correction_count=0,  # Decreased (potential regression)
            uncertainty_markers=5,  # Increased
            confidence_markers=1,  # Decreased
            hedging_ratio=0.8,  # Increased (more uncertain)
            verification_steps=0,  # Decreased (potential regression)
            output_length=800,  # Increased
            structured_output=True,  # Changed
        )

    def test_diff_basic(self, baseline_fp, current_fp):
        """Test basic diff computation."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        assert isinstance(diff, BehaviorDiff)
        assert diff.baseline_id == baseline_fp.trace_id
        assert diff.current_id == current_fp.trace_id
        assert len(diff.changes) > 0

    def test_diff_detects_depth_change(self, baseline_fp, current_fp):
        """Test that depth change is detected."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        depth_changes = [c for c in diff.changes if c.metric == "depth"]
        assert len(depth_changes) == 1
        assert depth_changes[0].change_type == ChangeType.DECREASED
        assert depth_changes[0].baseline_value == 5
        assert depth_changes[0].current_value == 3

    def test_diff_detects_tool_sequence_change(self, baseline_fp, current_fp):
        """Test that tool sequence change is detected."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        seq_changes = [c for c in diff.changes if c.metric == "tool_call_sequence"]
        assert len(seq_changes) == 1

    def test_diff_detects_verification_change(self, baseline_fp, current_fp):
        """Test that verification step decrease is detected."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        ver_changes = [c for c in diff.changes if c.metric == "verification_steps"]
        assert len(ver_changes) == 1
        assert ver_changes[0].change_type == ChangeType.DECREASED

    def test_diff_calculates_drift_score(self, baseline_fp, current_fp):
        """Test that drift score is calculated."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        assert 0 <= diff.drift_score <= 1
        assert diff.drift_score > 0  # Should detect drift

    def test_diff_counts_breaking_changes(self, baseline_fp, current_fp):
        """Test that breaking changes are counted."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        # Should have some breaking changes given the significant differences
        assert diff.total_changes > 0

    def test_diff_generates_summary(self, baseline_fp, current_fp):
        """Test that summary is generated."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        assert diff.summary is not None
        assert len(diff.summary) > 0

    def test_diff_generates_recommendations(self, baseline_fp, current_fp):
        """Test that recommendations are generated."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        assert diff.recommendations is not None
        # Should have recommendations for the significant changes

    def test_diff_same_fingerprints(self, baseline_fp):
        """Test diffing identical fingerprints."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, baseline_fp)

        assert diff.drift_score < 0.1
        assert diff.significance == SignificanceLevel.NONE

    def test_diff_structred_output_change(self, baseline_fp, current_fp):
        """Test structured output change detection."""
        engine = DiffEngine()
        diff = engine.diff(baseline_fp, current_fp)

        struct_changes = [c for c in diff.changes if c.metric == "structured_output"]
        assert len(struct_changes) == 1
        assert struct_changes[0].change_type == ChangeType.ADDED


class TestDiffFormatter:
    """Tests for DiffFormatter."""

    @pytest.fixture
    def sample_diff(self):
        """Create sample diff for formatting tests."""
        return BehaviorDiff(
            baseline_id="baseline_123",
            current_id="current_456",
            baseline_task_id="test_task",
            current_task_id="test_task",
            changes=[
                BehaviorChange(
                    metric="depth",
                    baseline_value=5,
                    current_value=3,
                    change_type=ChangeType.DECREASED,
                    magnitude=2,
                    significance=SignificanceLevel.MODERATE,
                    description="depth: 5 → 3 (-2)",
                ),
                BehaviorChange(
                    metric="verification_steps",
                    baseline_value=2,
                    current_value=0,
                    change_type=ChangeType.DECREASED,
                    magnitude=2,
                    significance=SignificanceLevel.MAJOR,
                    description="verification_steps: 2 → 0 (-2)",
                ),
            ],
            drift_score=0.45,
            significance=SignificanceLevel.MODERATE,
            total_changes=2,
            breaking_changes=1,
            summary="Drift score: 45%. Detected 1 major change(s), 1 moderate change(s).",
            recommendations=["⚠️ Verification steps decreased - model may be less thorough"],
        )

    def test_format_plain(self, sample_diff):
        """Test plain text formatting."""
        formatter = DiffFormatter()
        output = formatter.format_plain(sample_diff)

        assert "BEHAVIOR DIFF" in output
        assert "MODERATE" in output
        assert "depth" in output
        assert "verification_steps" in output

    def test_format_dict(self, sample_diff):
        """Test dict formatting."""
        formatter = DiffFormatter()
        output = formatter.format_dict(sample_diff)

        assert isinstance(output, dict)
        assert output["baseline_id"] == "baseline_123"
        assert output["drift_score"] == 0.45
        assert len(output["changes"]) == 2

    def test_format_json(self, sample_diff):
        """Test JSON formatting."""
        import json

        formatter = DiffFormatter()
        output = formatter.format_json(sample_diff)

        # Should be valid JSON
        parsed = json.loads(output)
        assert parsed["drift_score"] == 0.45
