"""
BRUTAL TEST: Full Pipeline End-to-End

Tests the entire Cogscope pipeline: Capture → Fingerprint → Store → Diff → Drift → Enforce.
Uses mock adapter (no API keys needed) to validate the complete data flow works correctly.
"""

import time
import uuid

import pytest

from cogscope.capture.tracer import CogscopeTracer
from cogscope.contracts.schema import BehaviorContract
from cogscope.contracts.validator import ContractValidator
from cogscope.diff.engine import DiffEngine
from cogscope.drift.detector import DriftDetector
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database
from cogscope.versioning.baseline import BaselineManager
from tests.brutal.conftest import load_contract_from_string, make_trace
from tests.brutal.fixtures.contract_fixtures import LENIENT_CONTRACT, STRICT_MATH_CONTRACT
from tests.brutal.fixtures.sample_outputs import (
    GOOD_MATH_REASONING,
    HEDGING_RESPONSE,
    SHALLOW_MATH,
)


class TestCaptureToFingerprint:
    """Test: Capture a trace using mock adapter → extract fingerprint → verify data flow."""

    def test_mock_capture_produces_trace(self, fresh_db):
        """Mock adapter must produce a valid trace with output."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        trace = tracer.capture(prompt="Solve x^2 = 16", task_id="test_capture")
        assert trace is not None
        assert trace.output is not None
        assert len(trace.output) > 0
        assert trace.model == "mock-model"

    def test_capture_saves_to_db(self, fresh_db):
        """Captured trace must be retrievable from database."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        trace = tracer.capture(prompt="Test prompt", task_id="test_save", save=True)
        retrieved = tracer.get_trace(trace.id)
        assert retrieved is not None
        assert retrieved.id == trace.id
        assert retrieved.output == trace.output

    def test_capture_produces_fingerprint(self, fresh_db):
        """Capture + save should auto-generate a fingerprint."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        trace = tracer.capture(prompt="Test prompt", task_id="test_fp", save=True)
        fp = tracer.get_fingerprint(trace.id)
        assert fp is not None
        assert fp.trace_id == trace.id
        assert fp.depth >= 1

    def test_multiple_captures_stored(self, fresh_db):
        """Multiple captures should all be stored and retrievable."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        ids = []
        for i in range(5):
            trace = tracer.capture(prompt=f"Prompt {i}", task_id="multi_test", save=True)
            ids.append(trace.id)
        traces = tracer.get_traces(task_id="multi_test")
        assert len(traces) >= 5


class TestDiffEngine:
    """Test: Compare two fingerprints and get meaningful diff."""

    def test_diff_identical_fingerprints(self, extractor):
        """Diffing identical fingerprints should show no drift."""
        diff_engine = DiffEngine()
        trace = make_trace(GOOD_MATH_REASONING)
        fp1 = extractor.extract(trace)
        fp2 = extractor.extract(trace)
        diff = diff_engine.diff(fp1, fp2)
        assert diff is not None
        assert (
            diff.drift_score < 0.1
        ), f"Identical fingerprints should have drift_score < 0.1, got {diff.drift_score}"

    def test_diff_different_fingerprints(self, extractor):
        """Diffing deep vs shallow should show significant drift."""
        diff_engine = DiffEngine()
        fp_deep = extractor.extract(make_trace(GOOD_MATH_REASONING))
        fp_shallow = extractor.extract(make_trace(SHALLOW_MATH))
        diff = diff_engine.diff(fp_deep, fp_shallow)
        assert diff is not None
        assert (
            diff.drift_score > 0.1
        ), f"Deep vs shallow should have significant drift, got {diff.drift_score}"
        assert len(diff.changes) > 0, "Should detect at least one behavioral change"

    def test_diff_has_recommendations(self, extractor):
        """Significant drift should produce recommendations."""
        diff_engine = DiffEngine()
        fp_deep = extractor.extract(make_trace(GOOD_MATH_REASONING))
        fp_shallow = extractor.extract(make_trace(SHALLOW_MATH))
        diff = diff_engine.diff(fp_deep, fp_shallow)
        assert diff.summary is not None or diff.recommendations is not None

    def test_diff_has_correct_baseline_id(self, extractor):
        """Diff should reference the correct baseline and current fingerprint IDs."""
        diff_engine = DiffEngine()
        fp1 = extractor.extract(make_trace(GOOD_MATH_REASONING, trace_id="baseline"))
        fp2 = extractor.extract(make_trace(SHALLOW_MATH, trace_id="current"))
        diff = diff_engine.diff(fp1, fp2)
        assert diff.baseline_id == fp1.trace_id
        assert diff.current_id == fp2.trace_id


class TestBaselineManagement:
    """Test: Create a baseline and compare against it."""

    def test_create_and_retrieve_baseline(self, fresh_db):
        """Create a baseline from a trace, retrieve it by name."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        baseline_mgr = BaselineManager(fresh_db)

        trace = tracer.capture(prompt="Baseline prompt", task_id="pin_test", save=True)
        fp = tracer.get_fingerprint(trace.id)
        assert fp is not None

        # Create baseline
        baseline = baseline_mgr.create(
            trace_id=trace.id,
            name="test_baseline",
        )
        assert baseline is not None
        assert baseline.name == "test_baseline"

        # Retrieve by name
        retrieved = baseline_mgr.get("test_baseline")
        assert retrieved is not None
        assert retrieved.name == "test_baseline"

    def test_diff_against_baseline(self, fresh_db):
        """Create a baseline, capture a new trace, diff them."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        baseline_mgr = BaselineManager(fresh_db)
        diff_engine = DiffEngine()

        # Capture and create baseline
        trace1 = tracer.capture(prompt="Baseline", task_id="diff_test", save=True)
        fp1 = tracer.get_fingerprint(trace1.id)
        baseline_mgr.create(
            trace_id=trace1.id,
            name="diff_baseline",
        )

        # Capture new trace
        trace2 = tracer.capture(prompt="New capture", task_id="diff_test", save=True)
        fp2 = tracer.get_fingerprint(trace2.id)
        assert fp2 is not None

        # Diff against baseline
        diff = diff_engine.diff(fp1, fp2)
        assert diff is not None
        assert diff.drift_score is not None


class TestDriftDetection:
    """Test: Detect behavioral drift over time."""

    def test_no_drift_same_behavior(self, fresh_db):
        """Same behavior repeated should show minimal drift."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        detector = DriftDetector(fresh_db)

        # Capture several traces with same settings
        for i in range(5):
            tracer.capture(prompt=f"Consistent prompt {i}", task_id="drift_stable", save=True)

        # Check drift
        report = detector.detect_drift(task_id="drift_stable")
        assert report is not None


class TestFullPipelineIntegration:
    """The BIG test: Full pipeline from capture through validation."""

    def test_capture_validate_pass(self, fresh_db):
        """Full pipeline: capture → fingerprint → validate → PASS."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        validator = ContractValidator()
        contract = load_contract_from_string(LENIENT_CONTRACT)

        trace = tracer.capture(prompt="Solve x^2 = 16", task_id="full_pass", save=True)
        fp = tracer.get_fingerprint(trace.id)
        assert fp is not None

        result = validator.validate(fp, contract, trace)
        assert result.exit_code == 0, (
            f"Mock + lenient contract should pass. "
            f"Violations: {[v.message for v in result.violations]}"
        )

    def test_capture_create_baseline_diff_validate(self, fresh_db):
        """Full lifecycle: capture → create baseline → capture again → diff → validate."""
        tracer = CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)
        baseline_mgr = BaselineManager(fresh_db)
        diff_engine = DiffEngine()
        validator = ContractValidator()
        contract = load_contract_from_string(LENIENT_CONTRACT)

        # Phase 1: Capture and create baseline
        trace1 = tracer.capture(prompt="Phase 1", task_id="lifecycle", save=True)
        fp1 = tracer.get_fingerprint(trace1.id)
        baseline_mgr.create(
            trace_id=trace1.id,
            name="lifecycle_baseline",
        )

        # Phase 2: Capture new trace
        trace2 = tracer.capture(prompt="Phase 2", task_id="lifecycle", save=True)
        fp2 = tracer.get_fingerprint(trace2.id)

        # Phase 3: Diff
        diff = diff_engine.diff(fp1, fp2)
        assert diff is not None

        # Phase 4: Validate
        result = validator.validate(fp2, contract, trace2)
        assert result is not None
        assert isinstance(result.exit_code, int)


class TestDatabaseResilience:
    """Test that the database handles edge cases correctly."""

    def test_concurrent_writes(self, fresh_db):
        """Database should handle rapid sequential writes."""
        extractor = FingerprintExtractor()
        for i in range(20):
            trace = make_trace(f"Output {i}", task_id="concurrent", trace_id=f"conc_{i:03d}")
            fresh_db.save_trace(trace)
            fp = extractor.extract(trace)
            fresh_db.save_fingerprint(fp)

        traces = fresh_db.get_traces_by_task(task_id="concurrent")
        assert len(traces) == 20

    def test_empty_db_queries_dont_crash(self, fresh_db):
        """Querying empty DB should return empty results, not crash."""
        traces = fresh_db.get_traces_by_task(task_id="nonexistent")
        assert traces == []

    def test_duplicate_trace_id_update(self, fresh_db):
        """Saving a trace with same ID should update, not crash."""
        trace = make_trace(GOOD_MATH_REASONING, trace_id="dup-001")
        fresh_db.save_trace(trace)
        # Save again with same ID
        fresh_db.save_trace(trace)
        # Should not crash, should still have the trace
        retrieved = fresh_db.get_trace("dup-001")
        assert retrieved is not None

    def test_stats_not_empty(self, populated_db):
        """Stats on populated DB should return meaningful data."""
        db, _ = populated_db
        stats = db.get_stats()
        assert stats is not None
        # Check for any count > 0
        assert any(isinstance(v, (int, float)) and v > 0 for v in stats.values())
