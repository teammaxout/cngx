"""Tests for behavior policies and enforcement.

Tests cover:
- Contract schema with BLOCK severity
- Deployment blocking behavior
- CI mode exit codes
- Cross-model enforcement
"""

from datetime import datetime
from pathlib import Path

import pytest

from cngx.contracts import (
    BehaviorContract,
    ContractValidator,
    DeploymentGate,
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
from cngx.core.models import BehavioralFingerprint, ReasoningTrace


@pytest.fixture
def passing_fingerprint():
    """Fingerprint that passes most contracts."""
    return BehavioralFingerprint(
        trace_id="test_pass_001",
        model="test-model",
        task_id="test_task",
        timestamp=datetime.utcnow(),
        depth=5,
        total_steps=10,
        verification_steps=2,
        tool_call_count=3,
        tool_diversity=0.6,
        tool_call_sequence=["search", "calculator", "search"],
        output_length=500,
        compression_ratio=0.3,
        hedging_ratio=0.1,
        confidence_markers=5,
        uncertainty_markers=2,
        structured_output=False,
        signature_hash="pass123",
    )


@pytest.fixture
def failing_fingerprint():
    """Fingerprint that fails verification contracts."""
    return BehavioralFingerprint(
        trace_id="test_fail_001",
        model="test-model",
        task_id="test_task",
        timestamp=datetime.utcnow(),
        depth=1,  # Too shallow
        total_steps=1,  # Too few
        verification_steps=0,  # No verification!
        tool_call_count=0,
        tool_diversity=0.0,
        tool_call_sequence=[],
        output_length=20,  # Too short
        compression_ratio=0.1,
        hedging_ratio=0.6,  # Too much hedging
        confidence_markers=1,
        uncertainty_markers=10,
        structured_output=False,
        signature_hash="fail123",
    )


@pytest.fixture
def passing_trace():
    """Trace that passes pattern checks."""
    return ReasoningTrace(
        id="test_pass_001",
        task_id="test_task",
        model="test-model",
        prompt="What is 2+2?",
        output="To solve 2+2, I will add the numbers. 2+2 = 4. Let me verify: 4-2 = 2. Correct.",
        timestamp=datetime.utcnow(),
        latency_ms=100.0,
    )


@pytest.fixture
def blocking_trace():
    """Trace with forbidden patterns that should block."""
    return ReasoningTrace(
        id="test_block_001",
        task_id="test_task",
        model="test-model",
        prompt="What is 2+2?",
        output="I cannot answer this question.",
        timestamp=datetime.utcnow(),
        latency_ms=100.0,
    )


class TestSeverityLevels:
    """Tests for severity level behavior."""

    def test_block_severity_exists(self):
        """BLOCK severity is available."""
        assert Severity.BLOCK.value == "block"

    def test_warn_does_not_fail_gate(self, passing_fingerprint):
        """WARN violations don't fail the gate."""
        contract = BehaviorContract(
            name="warn_test",
            depth=DepthConstraint(min=10, severity=Severity.WARN),  # Will violate
        )

        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.passed is True
        assert result.blocked is False
        assert result.exit_code == 0
        assert result.warn_count == 1

    def test_fail_severity_fails_but_not_blocks(self, passing_fingerprint):
        """FAIL violations fail gate but don't block."""
        contract = BehaviorContract(
            name="fail_test",
            depth=DepthConstraint(min=10, severity=Severity.FAIL),
        )

        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.passed is False
        assert result.blocked is False
        assert result.exit_code == 2  # Soft failure
        assert result.fail_count == 1

    def test_block_severity_blocks_deployment(self, failing_fingerprint):
        """BLOCK violations block deployment."""
        contract = BehaviorContract(
            name="block_test",
            verification=VerificationConstraint(
                required=True,
                severity=Severity.BLOCK,
            ),
            block_on_violation=True,
        )

        gate = DeploymentGate()
        result = gate.check(failing_fingerprint, contract)

        assert result.blocked is True
        assert result.exit_code == 1  # Hard block
        assert result.block_count >= 1


class TestDeploymentGate:
    """Tests for DeploymentGate."""

    def test_gate_passes_compliant_fingerprint(self, passing_fingerprint):
        """Gate passes when fingerprint meets contract."""
        contract = BehaviorContract(
            name="pass_test",
            depth=DepthConstraint(min=2, max=10),
            steps=StepsConstraint(min=5),
        )

        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.passed is True
        assert result.blocked is False
        assert result.exit_code == 0

    def test_gate_blocks_on_missing_verification(self, failing_fingerprint):
        """Gate blocks when verification is required but missing."""
        contract = BehaviorContract(
            name="verify_required",
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
                rationale="Math must be verified",
            ),
        )

        gate = DeploymentGate()
        result = gate.check(failing_fingerprint, contract)

        assert result.blocked is True
        assert result.exit_code == 1

        # Check violation details
        block_violations = [v for v in result.violations if v.severity == Severity.BLOCK]
        assert len(block_violations) >= 1
        assert any("verification" in v.constraint for v in block_violations)

    def test_gate_blocks_on_forbidden_pattern(self, passing_fingerprint, blocking_trace):
        """Gate blocks when forbidden pattern found."""
        contract = BehaviorContract(
            name="pattern_test",
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern="I cannot",
                    description="Must not refuse",
                    severity=Severity.BLOCK,
                ),
            ],
        )

        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract, blocking_trace)

        assert result.blocked is True
        assert result.exit_code == 1


class TestExitCodes:
    """Tests for CI/CD exit codes."""

    def test_exit_code_0_on_pass(self, passing_fingerprint):
        """Exit code 0 when gate passes."""
        contract = BehaviorContract(name="pass")
        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.exit_code == 0

    def test_exit_code_1_on_block(self, failing_fingerprint):
        """Exit code 1 when deployment blocked."""
        contract = BehaviorContract(
            name="block",
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )
        gate = DeploymentGate()
        result = gate.check(failing_fingerprint, contract)

        assert result.exit_code == 1

    def test_exit_code_2_on_fail(self, passing_fingerprint):
        """Exit code 2 on soft failure."""
        contract = BehaviorContract(
            name="fail",
            depth=DepthConstraint(min=100, severity=Severity.FAIL),
        )
        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.exit_code == 2


class TestGateResult:
    """Tests for GateResult output."""

    def test_result_has_contract_hash(self, passing_fingerprint):
        """GateResult includes contract hash for versioning."""
        contract = BehaviorContract(name="hash_test")
        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        assert result.contract_hash is not None
        assert len(result.contract_hash) == 16

    def test_result_to_ci_output(self, passing_fingerprint):
        """GateResult produces CI-friendly JSON output."""
        contract = BehaviorContract(name="ci_test")
        gate = DeploymentGate()
        result = gate.check(passing_fingerprint, contract)

        ci_output = result.to_ci_output()

        assert "passed" in ci_output
        assert "blocked" in ci_output
        assert "exit_code" in ci_output
        assert "violations" in ci_output
        assert "summary" in ci_output

    def test_result_report_readable(self, failing_fingerprint):
        """GateResult produces human-readable report."""
        contract = BehaviorContract(
            name="report_test",
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )
        gate = DeploymentGate()
        result = gate.check(failing_fingerprint, contract)

        report = result.report()

        assert "BLOCKED" in report
        assert "Policy:" in report or "report_test" in report
        assert "EXIT CODE: 1" in report


class TestContractSchema:
    """Tests for enhanced contract schema."""

    def test_domain_intent(self):
        """Contract supports domain metadata."""
        contract = BehaviorContract(
            name="domain_test",
            domain=DomainIntent.MATH,
            intent="Ensure math correctness",
        )

        assert contract.domain == DomainIntent.MATH
        assert "math" in contract.intent.lower()

    def test_constraint_rationale(self):
        """Constraints have rationale field."""
        constraint = VerificationConstraint(
            required=True,
            severity=Severity.BLOCK,
            rationale="Math must be verified to catch errors",
        )

        assert "verified" in constraint.rationale

    def test_contract_hash_deterministic(self):
        """Same contract produces same hash."""
        contract1 = BehaviorContract(name="hash", depth=DepthConstraint(min=3))
        contract2 = BehaviorContract(name="hash", depth=DepthConstraint(min=3))

        assert contract1.get_hash() == contract2.get_hash()

    def test_contract_hash_changes_on_modification(self):
        """Different contracts produce different hashes."""
        contract1 = BehaviorContract(name="hash", depth=DepthConstraint(min=3))
        contract2 = BehaviorContract(name="hash", depth=DepthConstraint(min=5))

        assert contract1.get_hash() != contract2.get_hash()

    def test_applies_to_filtering(self):
        """Contract scope filtering works."""
        contract = BehaviorContract(
            name="scoped",
            task_ids=["math_task"],
            models=["gpt-4"],
        )

        assert contract.applies_to("math_task", "gpt-4") is True
        assert contract.applies_to("other_task", "gpt-4") is False
        assert contract.applies_to("math_task", "claude") is False


class TestViolations:
    """Tests for Violation objects."""

    def test_violation_is_blocking(self):
        """Violation knows if it blocks deployment."""
        block_v = Violation(
            constraint="test",
            severity=Severity.BLOCK,
            message="Blocked",
        )
        warn_v = Violation(
            constraint="test",
            severity=Severity.WARN,
            message="Warned",
        )

        assert block_v.is_blocking() is True
        assert warn_v.is_blocking() is False

    def test_violation_includes_rationale(self, failing_fingerprint):
        """Violations include constraint rationale."""
        contract = BehaviorContract(
            name="rationale_test",
            verification=VerificationConstraint(
                required=True,
                severity=Severity.BLOCK,
                rationale="CUSTOM RATIONALE HERE",
            ),
        )

        validator = ContractValidator()
        result = validator.validate(failing_fingerprint, contract)

        # Find the verification violation
        v = next(v for v in result.violations if "verification" in v.constraint)
        assert "CUSTOM RATIONALE" in v.rationale


class TestCanonicalContracts:
    """Tests that canonical contracts are valid."""

    def test_math_correctness_loads(self, tmp_path):
        """Math correctness contract loads correctly."""
        contract_path = Path("examples/contracts/legacy/math_correctness.yaml")
        if contract_path.exists():
            contract = BehaviorContract.from_yaml(contract_path)
            assert contract.name == "math_correctness"
            assert contract.domain == DomainIntent.MATH
            assert contract.verification is not None
            assert contract.verification.required is True
            assert contract.verification.severity == Severity.BLOCK

    def test_research_reasoning_loads(self, tmp_path):
        """Research reasoning contract loads correctly."""
        contract_path = Path("examples/contracts/legacy/research_reasoning.yaml")
        if contract_path.exists():
            contract = BehaviorContract.from_yaml(contract_path)
            assert contract.name == "research_reasoning"
            assert contract.domain == DomainIntent.RESEARCH

    def test_code_correctness_loads(self, tmp_path):
        """Code correctness contract loads correctly."""
        contract_path = Path("examples/contracts/legacy/code_correctness.yaml")
        if contract_path.exists():
            contract = BehaviorContract.from_yaml(contract_path)
            assert contract.name == "code_correctness"
            assert contract.domain == DomainIntent.CODE


class TestCrossModelEnforcement:
    """Tests for cross-model contract enforcement."""

    def test_same_contract_different_fingerprints(self, passing_fingerprint, failing_fingerprint):
        """Same contract validates different model behaviors consistently."""
        contract = BehaviorContract(
            name="cross_model",
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )

        gate = DeploymentGate()

        passing_result = gate.check(passing_fingerprint, contract)
        failing_result = gate.check(failing_fingerprint, contract)

        assert passing_result.passed is True
        assert failing_result.blocked is True

        # Deterministic
        assert passing_result.exit_code == 0
        assert failing_result.exit_code == 1
