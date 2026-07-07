"""Unit tests for contract schema and validation.

Tests BehaviorContract parsing, constraint validation,
GateResult logic, and pattern matching enforcement.
"""

import tempfile
from pathlib import Path

import pytest

from cogscope.contracts.schema import (
    BehaviorContract,
    DepthConstraint,
    DomainIntent,
    ForbiddenPattern,
    GateResult,
    OutputConstraint,
    RequiredPattern,
    Severity,
    StepsConstraint,
    ToolConstraint,
    UncertaintyConstraint,
    VerificationConstraint,
    Violation,
)
from cogscope.contracts.validator import ContractValidator
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_contract():
    """A minimal contract with depth constraint."""
    return BehaviorContract(
        name="test_contract",
        version="1.0.0",
        description="Test contract",
        depth=DepthConstraint(min=3, severity=Severity.FAIL),
    )


@pytest.fixture
def strict_contract():
    """Contract with block-level constraints."""
    return BehaviorContract(
        name="strict_contract",
        version="1.0.0",
        description="Strict contract",
        depth=DepthConstraint(min=5, severity=Severity.BLOCK),
        uncertainty=UncertaintyConstraint(max_hedging_ratio=0.5, severity=Severity.FAIL),
        verification=VerificationConstraint(required=True, min_steps=1, severity=Severity.WARN),
    )


@pytest.fixture
def pattern_contract():
    """Contract with forbidden/required patterns."""
    return BehaviorContract(
        name="pattern_contract",
        version="1.0.0",
        forbidden_patterns=[
            ForbiddenPattern(pattern="I don't know", severity=Severity.BLOCK),
            ForbiddenPattern(pattern="I cannot", severity=Severity.BLOCK),
        ],
        required_patterns=[
            RequiredPattern(pattern="therefore", severity=Severity.FAIL),
        ],
    )


@pytest.fixture
def passing_fp():
    return BehavioralFingerprint(
        trace_id="pass_trace",
        task_id="test",
        depth=6,
        branching_factor=0.5,
        total_steps=6,
        tool_call_count=2,
        tool_call_sequence=["search"],
        tool_diversity=1.0,
        correction_count=1,
        uncertainty_markers=1,
        confidence_markers=3,
        hedging_ratio=0.3,
        verification_steps=2,
        output_length=500,
        structured_output=False,
    )


@pytest.fixture
def failing_fp():
    return BehavioralFingerprint(
        trace_id="fail_trace",
        task_id="test",
        depth=2,
        branching_factor=0.1,
        total_steps=2,
        tool_call_count=0,
        tool_call_sequence=[],
        tool_diversity=0.0,
        correction_count=0,
        uncertainty_markers=5,
        confidence_markers=0,
        hedging_ratio=0.9,
        verification_steps=0,
        output_length=50,
        structured_output=False,
    )


# ---------------------------------------------------------------------------
# BehaviorContract parsing
# ---------------------------------------------------------------------------


class TestBehaviorContract:
    def test_from_yaml_file(self, tmp_path):
        yaml_content = """
name: test
version: "1.0.0"
description: A test contract
depth:
  min: 3
  severity: fail
"""
        f = tmp_path / "contract.yaml"
        f.write_text(yaml_content)
        contract = BehaviorContract.from_yaml(f)
        assert contract.name == "test"
        assert contract.depth is not None
        assert contract.depth.min == 3

    def test_severity_values(self):
        assert Severity.BLOCK.value == "block"
        assert Severity.FAIL.value == "fail"
        assert Severity.WARN.value == "warn"

    def test_domain_intent(self):
        assert DomainIntent.MATH.value == "math"
        assert DomainIntent.CODE.value == "code"

    def test_contract_with_patterns(self, pattern_contract):
        assert len(pattern_contract.forbidden_patterns) == 2
        assert len(pattern_contract.required_patterns) == 1

    def test_contract_hash_deterministic(self, simple_contract):
        h1 = simple_contract.get_hash()
        h2 = simple_contract.get_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_contract_applies_to(self):
        contract = BehaviorContract(
            name="scoped",
            version="1.0.0",
            task_ids=["math_task"],
            models=["gpt-4o"],
        )
        assert contract.applies_to("math_task", "gpt-4o") is True
        assert contract.applies_to("other_task", "gpt-4o") is False
        assert contract.applies_to("math_task", "claude-3") is False

    def test_contract_to_yaml_and_back(self, simple_contract, tmp_path):
        out = tmp_path / "export.yaml"
        simple_contract.to_yaml(out)
        loaded = BehaviorContract.from_yaml(out)
        assert loaded.name == simple_contract.name

    def test_contract_to_json_and_back(self, simple_contract, tmp_path):
        out = tmp_path / "export.json"
        simple_contract.to_json(out)
        loaded = BehaviorContract.from_json(out)
        assert loaded.name == simple_contract.name


# ---------------------------------------------------------------------------
# ContractValidator
# ---------------------------------------------------------------------------


class TestContractValidator:
    def test_passing_fingerprint(self, simple_contract, passing_fp):
        v = ContractValidator()
        result = v.validate(passing_fp, simple_contract)
        assert result.passed is True
        assert result.blocked is False
        assert result.exit_code == 0

    def test_failing_fingerprint(self, simple_contract, failing_fp):
        v = ContractValidator()
        result = v.validate(failing_fp, simple_contract)
        assert result.passed is False
        assert result.exit_code != 0

    def test_block_violation(self, strict_contract, failing_fp):
        v = ContractValidator()
        result = v.validate(failing_fp, strict_contract)
        assert result.blocked is True
        assert result.block_count >= 1

    def test_warn_does_not_fail(self, passing_fp):
        """Warn-only violations should not cause failure."""
        contract = BehaviorContract(
            name="warn_only",
            version="1.0.0",
            verification=VerificationConstraint(
                required=True,
                min_steps=100,
                severity=Severity.WARN,
            ),
        )
        v = ContractValidator()
        result = v.validate(passing_fp, contract)
        assert result.passed is True  # Warns don't block
        assert result.warn_count >= 1

    def test_forbidden_pattern_detected(self, pattern_contract):
        v = ContractValidator()
        trace = ReasoningTrace(
            id="t1",
            task_id="test",
            model="test",
            prompt="test",
            output="I don't know the answer",
        )
        fp = BehavioralFingerprint(
            trace_id="t1",
            task_id="test",
            depth=3,
            branching_factor=0.5,
            total_steps=3,
            tool_call_count=0,
            tool_call_sequence=[],
            tool_diversity=0.0,
            correction_count=0,
            uncertainty_markers=0,
            confidence_markers=0,
            hedging_ratio=0.0,
            verification_steps=0,
            output_length=30,
            structured_output=False,
        )
        result = v.validate(fp, pattern_contract, trace=trace)
        # Should flag the forbidden pattern
        block_violations = [vi for vi in result.violations if vi.severity == Severity.BLOCK]
        assert len(block_violations) >= 1


# ---------------------------------------------------------------------------
# Violation and GateResult
# ---------------------------------------------------------------------------


class TestViolation:
    def test_violation_str_block(self):
        v = Violation(
            constraint="depth",
            severity=Severity.BLOCK,
            message="Depth too shallow",
        )
        assert "BLOCKED" in str(v)

    def test_violation_is_blocking(self):
        v = Violation(constraint="depth", severity=Severity.BLOCK, message="bad")
        assert v.is_blocking() is True

    def test_violation_not_blocking(self):
        v = Violation(constraint="depth", severity=Severity.WARN, message="ok")
        assert v.is_blocking() is False


class TestGateResult:
    def test_gate_result_passed(self):
        result = GateResult(
            contract_name="test",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t1",
            model="gpt-4o",
            task_id="test",
            passed=True,
            blocked=False,
            exit_code=0,
        )
        assert result.passed is True
        assert "PASSED" in str(result)

    def test_gate_result_blocked(self):
        result = GateResult(
            contract_name="test",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t1",
            model="gpt-4o",
            task_id="test",
            passed=False,
            blocked=True,
            exit_code=2,
            block_count=1,
        )
        assert result.exit_code == 2
        assert "BLOCKED" in str(result)

    def test_gate_result_ci_output(self):
        result = GateResult(
            contract_name="math",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t1",
            model="gpt-4o",
            task_id="test",
            passed=True,
            exit_code=0,
        )
        ci = result.to_ci_output()
        assert ci["passed"] is True
        assert ci["contract"] == "math"
        assert ci["exit_code"] == 0

    def test_gate_result_report(self):
        result = GateResult(
            contract_name="math",
            contract_version="1.0.0",
            contract_hash="abc123",
            trace_id="t1",
            model="gpt-4o",
            task_id="test",
            passed=False,
            blocked=True,
            exit_code=2,
            block_count=1,
            violations=[
                Violation(constraint="depth", severity=Severity.BLOCK, message="Too shallow"),
            ],
        )
        report = result.report()
        assert "BLOCKED" in report
        assert "Too shallow" in report
