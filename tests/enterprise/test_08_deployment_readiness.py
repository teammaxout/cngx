"""
Enterprise Test: Deployment Readiness

Verifies everything needed for production deployment:
- Module imports & exports
- Configuration system
- Database initialization / cleanup
- Contract loading from files
- Fingerprint vector consistency
- Calibration system
- Server app creation
- Docker configuration
"""

import importlib
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from cngx.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorDiff,
    ChangeType,
    DriftReport,
    EvalResult,
    EvalSuite,
    ModelConfig,
    ReasoningTrace,
    SignificanceLevel,
    TokenUsage,
)


class TestModuleImports:
    """All public modules import without error."""

    MODULES = [
        "cngx",
        "cngx.core.models",
        "cngx.capture.tracer",
        "cngx.capture.adapters.gemini",
        "cngx.fingerprint.extractor",
        "cngx.contracts.schema",
        "cngx.contracts.validator",
        "cngx.diff.engine",
        "cngx.drift.detector",
        "cngx.storage.database",
        "cngx.calibration.confidence",
        "cngx.calibration.profiles",
        "cngx.enforcement.gate",
        "cngx.server.app",
    ]

    @pytest.mark.parametrize("module_name", MODULES)
    def test_import(self, module_name):
        """Each module imports successfully."""
        mod = importlib.import_module(module_name)
        assert mod is not None


class TestCoreModels:
    """Core data models are well-formed and serializable."""

    def test_reasoning_trace_creation(self):
        """ReasoningTrace can be created with all fields."""
        trace = ReasoningTrace(
            id="test_001",
            timestamp=datetime.utcnow(),
            task_id="unit_test",
            model="gemini-2.5-flash",
            model_config_params=ModelConfig(temperature=0.3),
            prompt="Test prompt",
            output="Test output",
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
        assert trace.id == "test_001"
        assert trace.content_hash  # computed property
        assert len(trace.content_hash) == 16

    def test_behavioral_fingerprint_vector(self):
        """Fingerprint to_vector returns consistent 14-element vector."""
        fp = BehavioralFingerprint(
            trace_id="t1",
            task_id="test",
            timestamp=datetime.utcnow(),
            depth=5,
            total_steps=10,
            output_length=500,
        )
        vec = fp.to_vector()
        assert isinstance(vec, list)
        assert len(vec) == 14
        assert all(isinstance(v, (int, float)) for v in vec)

    def test_fingerprint_signature_hash(self):
        """Fingerprint signature_hash is deterministic."""
        fp1 = BehavioralFingerprint(
            trace_id="t1",
            task_id="test",
            timestamp=datetime.utcnow(),
            depth=5,
            total_steps=10,
        )
        fp2 = BehavioralFingerprint(
            trace_id="t1",
            task_id="test",
            timestamp=datetime.utcnow(),
            depth=5,
            total_steps=10,
        )
        assert fp1.signature_hash == fp2.signature_hash

    def test_behavior_diff_model(self):
        """BehaviorDiff has computable properties."""
        diff = BehaviorDiff(
            baseline_id="b1",
            current_id="c1",
            baseline_task_id="t1",
            current_task_id="t1",
            timestamp=datetime.utcnow(),
            drift_score=0.15,
            breaking_changes=0,
        )
        assert not diff.has_regression

        from cngx.core.models import BehaviorChange, ChangeType
        from cngx.core.models import SignificanceLevel as SigLevel

        diff2 = BehaviorDiff(
            baseline_id="b2",
            current_id="c2",
            baseline_task_id="t2",
            current_task_id="t2",
            timestamp=datetime.utcnow(),
            drift_score=0.5,
            breaking_changes=2,
            changes=[
                BehaviorChange(
                    metric="reasoning_depth",
                    baseline_value=8.0,
                    current_value=2.0,
                    change_type=ChangeType.DECREASED,
                    significance=SigLevel.CRITICAL,
                    description="Depth dropped",
                ),
            ],
        )
        assert diff2.has_regression

    def test_all_enums(self):
        """All enums have expected values."""
        assert SignificanceLevel.NONE.value == "none"
        assert SignificanceLevel.CRITICAL.value == "critical"
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.UNCHANGED.value == "unchanged"


class TestContractLoadingFromFile:
    """Contract YAML files load correctly."""

    def test_load_bundled_contracts(self):
        """All bundled contract YAML files load successfully."""
        from tests.enterprise.conftest import repo_root

        contracts_dir = repo_root() / "contracts"
        assert contracts_dir.is_dir(), f"contracts directory missing: {contracts_dir}"

        from cngx.contracts.schema import BehaviorContract

        yaml_files = list(contracts_dir.glob("*.yaml"))
        assert len(yaml_files) > 0, "Expected at least one contract file"

        for yaml_file in yaml_files:
            contract = BehaviorContract.from_yaml(yaml_file)
            assert contract.name, f"{yaml_file.name}: name missing"
            assert contract.version, f"{yaml_file.name}: version missing"

    def test_example_contracts_load(self):
        """Example contract YAML files load successfully."""
        from tests.enterprise.conftest import repo_root

        examples_dir = repo_root() / "examples" / "contracts"
        assert examples_dir.is_dir(), f"examples/contracts missing: {examples_dir}"

        from cngx.contracts.schema import BehaviorContract

        for yaml_file in examples_dir.glob("*.yaml"):
            contract = BehaviorContract.from_yaml(yaml_file)
            assert contract.name


class TestDatabaseLifecycle:
    """Database initialization, operations, and cleanup."""

    def test_create_and_close(self, tmp_path):
        """Database creates and closes cleanly."""
        from cngx.storage.database import Database

        db = Database(tmp_path / "test.duckdb")
        stats = db.get_stats()
        assert stats["traces"] == 0
        db.close()

    def test_multiple_databases(self, tmp_path):
        """Multiple database instances can coexist."""
        from cngx.storage.database import Database

        db1 = Database(tmp_path / "db1.duckdb")
        db2 = Database(tmp_path / "db2.duckdb")

        trace = ReasoningTrace(
            id="multi_db_test",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="test",
            output="test",
            token_usage=TokenUsage(),
        )
        db1.save_trace(trace)

        assert db1.get_stats()["traces"] == 1
        assert db2.get_stats()["traces"] == 0

        db1.close()
        db2.close()

    def test_trace_not_found_error(self, tmp_db):
        """Querying non-existent trace raises expected error."""
        with pytest.raises(Exception):  # TraceNotFoundError
            tmp_db.get_trace("nonexistent_id")


class TestCalibrationSystem:
    """Calibration engine and profiles work correctly."""

    def test_confidence_estimation(self):
        """Confidence estimator produces valid scores."""
        from cngx.calibration.confidence import ConfidenceCalibrator

        cal = ConfidenceCalibrator()
        fp_dict = {
            "hedging_ratio": 0.1,
            "verification_steps": 3,
            "uncertainty_markers": 1,
            "correction_count": 0,
            "structured_output": True,
            "tokens_per_step": 15.0,
        }
        score = cal.estimate_confidence(fp_dict)
        assert 0.0 <= score <= 1.0

    def test_model_profiles(self):
        """Known model profiles are available."""
        from cngx.calibration.profiles import (
            ModelFamily,
            get_profile,
            resolve_model_family,
        )

        family = resolve_model_family("gemini-2.5-flash")
        assert isinstance(family, ModelFamily)

        profile = get_profile("gemini-2.5-flash")
        assert profile is not None
        assert profile.display_name

    def test_adaptive_thresholds(self):
        """Adaptive thresholds adjust contract parameters by model."""
        from cngx.calibration.profiles import get_adaptive_thresholds

        thresholds = get_adaptive_thresholds("gemini-2.5-flash")
        # Should adjust depth/step constraints
        adjusted_min = thresholds.adjust_depth_min(3)
        assert isinstance(adjusted_min, int)
        assert adjusted_min >= 0

    def test_calibration_engine(self):
        """Calibration engine records observations and calibrates."""
        from cngx.calibration.profiles import CalibrationEngine

        engine = CalibrationEngine()
        for i in range(15):
            engine.observe(
                "test-model",
                {
                    "depth": 3 + i % 3,
                    "total_steps": 5 + i % 4,
                    "correction_count": i % 2,
                    "uncertainty_markers": i % 3,
                    "confidence_markers": 2 + i % 3,
                    "verification_steps": 1 + i % 2,
                    "output_length": 100 + i * 20,
                    "reasoning_length": 50 + i * 10,
                    "compression_ratio": 0.5 + i * 0.02,
                    "hedging_ratio": 0.1 + i * 0.01,
                    "tool_diversity": 0.5,
                },
            )

        profile = engine.calibrate("test-model", min_observations=10)
        assert profile is not None
        assert profile.display_name


class TestServerAppCreation:
    """FastAPI app can be created and has expected routes."""

    def test_app_is_fastapi(self):
        """Server app is a valid FastAPI instance."""
        from cngx.server.app import app

        assert app is not None
        # Check it has routes
        routes = [r.path for r in app.routes]
        assert "/" in routes or any("/" in str(r) for r in routes)

    def test_health_endpoint_exists(self):
        """Health endpoint is registered."""
        from cngx.server.app import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in routes

    def test_api_endpoints_exist(self):
        """Core API endpoints are registered."""
        from cngx.server.app import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        expected = ["/api/traces", "/api/baselines", "/api/diff"]
        for ep in expected:
            assert ep in routes, f"Missing endpoint: {ep}"


class TestDockerConfiguration:
    """Docker build files are valid."""

    def test_dockerfile_exists(self):
        """Dockerfile exists and has correct structure."""
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        assert dockerfile.exists()
        content = dockerfile.read_text()
        assert "FROM" in content
        assert "EXPOSE" in content or "CMD" in content

    def test_docker_compose_archived(self):
        """docker-compose.yml is not part of the OSS product surface."""
        root = Path(__file__).resolve().parents[2]
        assert not (root / "docker-compose.yml").exists()

    def test_pyproject_toml_valid(self):
        """pyproject.toml has correct metadata."""
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # Python < 3.11
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        assert "project" in data
        assert data["project"]["name"] == "cngx"
        from cngx import __version__

        assert data["project"]["version"] == __version__
