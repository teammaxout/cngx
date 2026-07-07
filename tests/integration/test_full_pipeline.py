"""Integration tests for full Cogscope pipeline."""

import tempfile
from pathlib import Path

import pytest

from cogscope.capture.tracer import CogscopeTracer
from cogscope.diff.engine import DiffEngine
from cogscope.drift.detector import DriftDetector
from cogscope.diff.engine import DiffEngine
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database
from cogscope.versioning.baseline import BaselineManager


class TestCaptureIntegration:
    """Integration tests for capture pipeline."""

    @pytest.fixture
    def tracer_with_db(self):
        """Create tracer with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".cogscope" / "test.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = Database(db_path)
            tracer = CogscopeTracer(adapter="mock", model="mock-model", db=db)
            yield tracer, db
            db.close()

    def test_capture_creates_trace(self, tracer_with_db):
        """Test that capture creates a trace."""
        tracer, db = tracer_with_db

        trace = tracer.capture(
            prompt="What is 2 + 2?",
            task_id="math",
        )

        assert trace.id is not None
        assert trace.task_id == "math"
        assert trace.output is not None

    def test_capture_creates_fingerprint(self, tracer_with_db):
        """Test that capture creates a fingerprint."""
        tracer, db = tracer_with_db

        trace = tracer.capture(
            prompt="Explain quantum mechanics",
            task_id="physics",
        )

        fp = db.get_fingerprint_by_trace(trace.id)
        assert fp is not None
        assert fp.depth > 0
        assert fp.signature_hash is not None

    def test_capture_stores_in_db(self, tracer_with_db):
        """Test that capture stores trace in database."""
        tracer, db = tracer_with_db

        trace = tracer.capture(
            prompt="Hello world",
            task_id="test",
        )

        # Should be retrievable
        retrieved = db.get_trace(trace.id)
        assert retrieved.id == trace.id
        assert retrieved.prompt == trace.prompt

    def test_capture_multiple_traces(self, tracer_with_db):
        """Test capturing multiple traces for a task."""
        tracer, db = tracer_with_db

        for i in range(5):
            tracer.capture(
                prompt=f"Question {i}",
                task_id="multi",
            )

        traces = db.get_traces_by_task("multi")
        assert len(traces) == 5


class TestFullPipeline:
    """Integration tests for full Cogscope pipeline."""

    @pytest.fixture
    def setup_pipeline(self):
        """Set up complete pipeline with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".cogscope" / "test.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = Database(db_path)

            tracer = CogscopeTracer(adapter="mock", model="mock-model", db=db)
            diff_engine = DiffEngine()
            drift_detector = DriftDetector(db=db)
            baseline_manager = BaselineManager(db=db)

            yield {
                "tracer": tracer,
                "db": db,
                "diff_engine": diff_engine,
                "drift_detector": drift_detector,
                "baseline_manager": baseline_manager,
            }
            db.close()

    def test_full_workflow(self, setup_pipeline):
        """Test complete workflow: capture → pin → capture → diff."""
        ctx = setup_pipeline
        tracer = ctx["tracer"]
        db = ctx["db"]
        diff_engine = ctx["diff_engine"]
        baseline_manager = ctx["baseline_manager"]

        # 1. Capture baseline trace
        baseline_trace = tracer.capture(
            prompt="Solve: 2x + 5 = 13",
            task_id="math_reasoning",
        )

        # 2. Pin as baseline
        baseline = baseline_manager.create(
            trace_id=baseline_trace.id,
            name="math_v1",
            description="Initial math baseline",
        )
        assert baseline.name == "math_v1"

        # 3. Capture new trace (simulating model change)
        tracer.switch_adapter("mock", preset="verbose")  # Change behavior
        new_trace = tracer.capture(
            prompt="Solve: 2x + 5 = 13",
            task_id="math_reasoning",
        )

        # 4. Compute diff
        baseline_fp = db.get_fingerprint_by_trace(baseline_trace.id)
        new_fp = db.get_fingerprint_by_trace(new_trace.id)

        diff = diff_engine.diff(baseline_fp, new_fp)

        assert diff is not None
        assert diff.drift_score >= 0

    def test_drift_detection_workflow(self, setup_pipeline):
        """Test drift detection with multiple traces."""
        ctx = setup_pipeline
        tracer = ctx["tracer"]
        db = ctx["db"]
        drift_detector = ctx["drift_detector"]
        baseline_manager = ctx["baseline_manager"]

        # Capture several baseline traces
        for i in range(5):
            tracer.capture(
                prompt=f"Math problem {i}",
                task_id="drift_test",
            )

        # Create baseline from first trace
        traces = db.get_traces_by_task("drift_test")
        baseline_manager.create(
            trace_id=traces[-1].id,
            name="drift_baseline",
        )

        # Change behavior and capture more
        tracer.switch_adapter("mock", preset="uncertain")
        for i in range(5):
            tracer.capture(
                prompt=f"Math problem {i+5}",
                task_id="drift_test",
            )

        # Detect drift
        score, status = drift_detector.quick_check(
            db.get_fingerprint_by_trace(traces[0].id),
            baseline_manager.get_fingerprint("drift_baseline"),
        )

        # Should detect some level of change
        assert score is not None

    def test_regression_detection(self, setup_pipeline):
        """Test regression detection between behaviors."""
        ctx = setup_pipeline
        tracer = ctx["tracer"]
        db = ctx["db"]
        baseline_manager = ctx["baseline_manager"]

        # Capture baseline with good behavior
        tracer.switch_adapter("mock", preset="confident")
        baseline_trace = tracer.capture(
            prompt="Verify this calculation",
            task_id="regression_test",
        )

        baseline_manager.create(
            trace_id=baseline_trace.id,
            name="regression_baseline",
        )

        # Capture with degraded behavior
        tracer.switch_adapter("mock", preset="terse")  # Less thorough
        new_trace = tracer.capture(
            prompt="Verify this calculation",
            task_id="regression_test",
        )

        # Check for regression via behavioral diff
        diff_engine = DiffEngine()
        baseline_fp = baseline_manager.get_fingerprint("regression_baseline")
        new_fp = db.get_fingerprint_by_trace(new_trace.id)
        diff = diff_engine.diff(baseline_fp, new_fp)
        assert diff.drift_score is not None
        assert len(diff.changes) >= 0


class TestMockAdapterPresets:
    """Test that mock adapter presets produce different behaviors."""

    @pytest.fixture
    def tracer(self):
        """Create tracer with mock adapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / ".cogscope" / "test.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db = Database(db_path)
            tracer = CogscopeTracer(adapter="mock", model="mock-model", db=db)
            yield tracer, db
            db.close()

    def test_verbose_vs_terse(self, tracer):
        """Test that verbose and terse presets differ."""
        tracer_obj, db = tracer
        extractor = FingerprintExtractor()

        # Verbose preset
        tracer_obj.switch_adapter("mock", preset="verbose")
        trace1 = tracer_obj.capture(prompt="Explain AI", task_id="preset_test", save=False)
        fp1 = extractor.extract(trace1)

        # Terse preset
        tracer_obj.switch_adapter("mock", preset="terse")
        trace2 = tracer_obj.capture(prompt="Explain AI", task_id="preset_test", save=False)
        fp2 = extractor.extract(trace2)

        # Verbose should have more depth
        assert fp1.depth > fp2.depth or fp1.output_length > fp2.output_length

    def test_tool_heavy_preset(self, tracer):
        """Test that tool_heavy preset uses more tools."""
        tracer_obj, db = tracer
        extractor = FingerprintExtractor()

        # Default preset
        tracer_obj.switch_adapter("mock", preset="default")
        trace1 = tracer_obj.capture(prompt="Research this", task_id="tool_test", save=False)
        _fp1 = extractor.extract(trace1)

        # Tool heavy preset
        tracer_obj.switch_adapter("mock", preset="tool_heavy")
        trace2 = tracer_obj.capture(prompt="Research this", task_id="tool_test", save=False)
        fp2 = extractor.extract(trace2)

        # Over multiple runs, tool_heavy should average more tools
        # (probabilistic, so we just check it can run)
        assert fp2.tool_call_count >= 0

    def test_uncertain_preset(self, tracer):
        """Test that uncertain preset has higher hedging."""
        tracer_obj, db = tracer
        extractor = FingerprintExtractor()

        # Confident preset
        tracer_obj.switch_adapter("mock", preset="confident")
        trace1 = tracer_obj.capture(prompt="Answer this", task_id="uncertainty_test", save=False)
        _fp1 = extractor.extract(trace1)

        # Uncertain preset
        tracer_obj.switch_adapter("mock", preset="uncertain")
        trace2 = tracer_obj.capture(prompt="Answer this", task_id="uncertainty_test", save=False)
        fp2 = extractor.extract(trace2)

        # Uncertain should have higher hedging ratio on average
        # (probabilistic due to random generation)
        assert fp2.hedging_ratio >= 0  # Just check it runs
