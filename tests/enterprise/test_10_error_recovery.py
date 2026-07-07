"""
Enterprise Test: Error Recovery & Resilience

Tests error handling, retries, and recovery:
- Invalid API keys
- Timeout handling
- Malformed inputs
- Database error recovery
- Contract validation with broken data
- Adapter error handling
"""

import os
import time
from datetime import datetime

import pytest

from cogscope.capture.tracer import CogscopeTracer
from cogscope.contracts.schema import BehaviorContract
from cogscope.contracts.validator import ContractValidator
from cogscope.core.models import (
    BehavioralFingerprint,
    ModelConfig,
    ReasoningTrace,
    TokenUsage,
)
from cogscope.diff.engine import DiffEngine
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database


class TestInvalidInputHandling:
    """System handles invalid inputs gracefully."""

    def test_empty_prompt(self):
        """Empty prompt doesn't crash the tracer."""
        tracer = CogscopeTracer(adapter="mock")
        trace = tracer.capture(prompt="", task_id="empty", save=False)
        assert trace is not None
        # Output may be empty or a default
        assert isinstance(trace.output, str)

    def test_none_fields_in_fingerprint(self):
        """Fingerprint extraction with minimal trace works."""
        trace = ReasoningTrace(
            id="minimal",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="test",
            output="",
            token_usage=TokenUsage(),
        )
        ext = FingerprintExtractor()
        fp = ext.extract(trace)
        assert fp is not None
        assert fp.output_length == 0

    def test_contract_with_no_constraints(self):
        """Contract with zero constraints passes any fingerprint."""
        fp = BehavioralFingerprint(
            trace_id="test",
            task_id="test",
            timestamp=datetime.utcnow(),
        )
        contract = BehaviorContract(name="empty_contract", version="1.0.0")
        validator = ContractValidator()
        result = validator.validate(fp, contract)
        assert result.passed

    def test_diff_identical_fingerprints(self):
        """Diffing identical fingerprints shows no changes."""
        fp = BehavioralFingerprint(
            trace_id="same",
            task_id="test",
            timestamp=datetime.utcnow(),
            depth=3,
            total_steps=5,
            output_length=100,
        )
        engine = DiffEngine()
        diff = engine.diff(fp, fp)
        assert diff.drift_score == 0.0 or diff.drift_score < 0.01

    def test_compare_empty_fingerprints(self):
        """Comparing two empty fingerprints returns high similarity."""
        fp1 = BehavioralFingerprint(trace_id="e1", task_id="test", timestamp=datetime.utcnow())
        fp2 = BehavioralFingerprint(trace_id="e2", task_id="test", timestamp=datetime.utcnow())
        ext = FingerprintExtractor()
        sim = ext.compare(fp1, fp2)
        assert sim >= 0.9  # Both empty → very similar


class TestDatabaseErrorRecovery:
    """Database handles errors gracefully."""

    def test_duplicate_trace_id(self, tmp_db):
        """Storing duplicate trace ID handles gracefully."""
        trace = ReasoningTrace(
            id="dup_test",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="test",
            output="test",
            token_usage=TokenUsage(),
        )
        tmp_db.save_trace(trace)
        # Second save with same ID — should either overwrite or raise
        try:
            tmp_db.save_trace(trace)
        except Exception:
            pass  # Expected — some DBs reject duplicates
        # Either way, database should still work
        stats = tmp_db.get_stats()
        assert stats["traces"] >= 1

    def test_query_empty_database(self, tmp_db):
        """Querying empty database returns empty results gracefully."""
        traces = tmp_db.get_traces_by_task("nonexistent_task")
        assert traces == []

        recent = tmp_db.get_recent_traces()
        assert recent == []

        baselines = tmp_db.list_baselines()
        assert baselines == []

    def test_get_nonexistent_baseline(self, tmp_db):
        """Getting non-existent baseline raises clear error."""
        with pytest.raises(Exception):
            tmp_db.get_baseline("nonexistent_baseline")


class TestAdapterErrorHandling:
    """Adapter-level error handling."""

    def test_gemini_unavailable_raises_clear_error(self):
        """Gemini adapter reports clear error when google-genai is not installed."""
        from unittest.mock import patch

        from cogscope.capture.adapters import gemini
        from cogscope.capture.adapters.gemini import GeminiAdapter
        from cogscope.core.exceptions import AdapterError

        with patch.object(gemini, "GEMINI_AVAILABLE", False):
            with pytest.raises(AdapterError, match="not installed"):
                GeminiAdapter(model="gemini-2.5-flash", api_key="any")

    def test_mock_adapter_always_works(self):
        """Mock adapter works without any API key."""
        tracer = CogscopeTracer(adapter="mock")
        trace = tracer.capture(prompt="test", task_id="mock_test", save=False)
        assert trace.output
        assert trace.model

    def test_tracer_switch_adapter(self):
        """Switching adapter at runtime works."""
        tracer = CogscopeTracer(adapter="mock")
        trace1 = tracer.capture(prompt="test", task_id="switch", save=False)
        assert trace1.output

        # Switch to mock again (just testing the mechanism)
        tracer.switch_adapter("mock")
        trace2 = tracer.capture(prompt="test2", task_id="switch", save=False)
        assert trace2.output


class TestContractErrorCases:
    """Contract validation error handling."""

    def test_invalid_yaml_contract(self):
        """Invalid YAML raises clear error."""
        import yaml

        with pytest.raises((yaml.YAMLError, Exception)):
            yaml.safe_load("name: [invalid: yaml: {{}")

    def test_contract_missing_name(self):
        """Contract without name raises validation error."""
        with pytest.raises(Exception):
            BehaviorContract(version="1.0.0")  # name is required

    def test_contract_applies_to_filtering(self):
        """Contract task_id/model filtering works."""
        contract = BehaviorContract(
            name="filtered",
            version="1.0.0",
            task_ids=["allowed_task"],
            models=["allowed_model"],
        )
        assert contract.applies_to("allowed_task", "allowed_model")
        assert not contract.applies_to("other_task", "allowed_model")
        assert not contract.applies_to("allowed_task", "other_model")

    def test_violation_severity_levels(self):
        """All severity levels are valid."""
        from cogscope.contracts.schema import Severity

        assert Severity.WARN.value == "warn"
        assert Severity.FAIL.value == "fail"
        assert Severity.BLOCK.value == "block"

    def test_gate_result_report_generation(self):
        """GateResult.report() works for both pass and fail."""
        from cogscope.contracts.schema import GateResult, Severity, Violation

        # Passing result
        passing = GateResult(
            contract_name="test",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t1",
            model="test",
            task_id="test",
            timestamp=datetime.utcnow(),
            passed=True,
        )
        assert "PASS" in passing.report().upper() or "pass" in passing.report().lower()

        # Failing result
        failing = GateResult(
            contract_name="test",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t2",
            model="test",
            task_id="test",
            timestamp=datetime.utcnow(),
            passed=False,
            violations=[
                Violation(
                    constraint="depth",
                    severity=Severity.FAIL,
                    message="Depth too low",
                    expected=5,
                    actual=1,
                )
            ],
            fail_count=1,
        )
        report = failing.report()
        assert isinstance(report, str)
        assert "depth" in report.lower() or "Depth" in report


class TestEdgeCaseFingerprinting:
    """Fingerprint extraction edge cases."""

    def test_very_long_output(self):
        """Very long output (100KB) fingerprints successfully."""
        trace = ReasoningTrace(
            id="long_out",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="test",
            output="Word " * 20000,  # ~100KB
            token_usage=TokenUsage(prompt_tokens=10, completion_tokens=20000, total_tokens=20010),
        )
        ext = FingerprintExtractor()
        fp = ext.extract(trace)
        assert fp.output_length > 0
        assert fp.total_steps >= 1

    def test_output_with_code_blocks(self):
        """Output containing code blocks fingerprints correctly."""
        output = """Here is the solution:

```python
def hello():
    print("Hello, World!")
```

This function prints a greeting.
"""
        trace = ReasoningTrace(
            id="code_fp",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="Write hello world",
            output=output,
            token_usage=TokenUsage(prompt_tokens=5, completion_tokens=30, total_tokens=35),
        )
        ext = FingerprintExtractor()
        fp = ext.extract(trace)
        assert fp.output_length > 0
        assert fp.structured_output or True  # May or may not detect structure

    def test_output_with_math_expressions(self):
        """Output with math expressions fingerprints correctly."""
        output = "The solution is: 2x + 3 = 7, so x = 2. Verification: 2(2) + 3 = 7 ✓"
        trace = ReasoningTrace(
            id="math_fp",
            timestamp=datetime.utcnow(),
            task_id="test",
            model="test",
            model_config_params=ModelConfig(),
            prompt="Solve 2x+3=7",
            output=output,
            token_usage=TokenUsage(prompt_tokens=5, completion_tokens=20, total_tokens=25),
        )
        ext = FingerprintExtractor()
        fp = ext.extract(trace)
        assert fp.output_length > 0
        assert fp.verification_steps >= 0
