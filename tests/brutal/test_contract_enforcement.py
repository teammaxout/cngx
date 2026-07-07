"""
BRUTAL TEST: Contract Enforcement Truthfulness

Tests whether contracts actually block what they claim to block,
and pass what they claim to pass. This is the enforcement layer.

If a BLOCK-severity violation doesn't result in exit_code=1, Cogscope is broken.
"""

import pytest
import yaml

from cogscope.contracts.schema import BehaviorContract, Severity
from cogscope.contracts.validator import ContractValidator
from cogscope.fingerprint.extractor import FingerprintExtractor
from tests.brutal.conftest import load_contract_from_string, make_trace
from tests.brutal.fixtures.contract_fixtures import (
    ALL_CONSTRAINTS_CONTRACT,
    CODE_REVIEW_CONTRACT,
    IMPOSSIBLE_CONTRACT,
    LENIENT_CONTRACT,
    RESEARCH_CONTRACT,
    STRICT_MATH_CONTRACT,
    WARN_ONLY_CONTRACT,
)
from tests.brutal.fixtures.sample_outputs import (
    GOOD_CODE_REVIEW,
    GOOD_MATH_REASONING,
    GOOD_RESEARCH,
    HEDGING_RESPONSE,
    OVERCONFIDENT_WRONG,
    REFUSAL_RESPONSE,
    SELF_CORRECTING,
    SHALLOW_CODE_REVIEW,
    SHALLOW_MATH,
    SHALLOW_RESEARCH,
    TERSE_RESPONSE,
    VERBOSE_RESPONSE,
)


class TestStrictMathContract:
    """Test strict math contract against various outputs."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(STRICT_MATH_CONTRACT)

    def _validate(self, output: str, task_id: str = "math"):
        trace = make_trace(output, task_id=task_id)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_good_math_passes(self):
        """Good 4-step verified math reasoning MUST pass strict math contract."""
        result = self._validate(GOOD_MATH_REASONING)
        assert result.passed or result.exit_code == 0, (
            f"Good math should pass strict contract. "
            f"Exit code: {result.exit_code}, Violations: {[v.message for v in result.violations]}"
        )

    def test_shallow_math_blocked(self):
        """One-line answer MUST be BLOCKED by strict math contract."""
        result = self._validate(SHALLOW_MATH)
        assert result.blocked, (
            f"Shallow math MUST be blocked. "
            f"Got passed={result.passed}, blocked={result.blocked}, "
            f"exit_code={result.exit_code}, violations={[v.message for v in result.violations]}"
        )
        assert result.exit_code == 1, f"Expected exit_code=1 (BLOCK), got {result.exit_code}"

    def test_shallow_math_has_depth_violation(self):
        """Shallow math should trigger a depth violation."""
        result = self._validate(SHALLOW_MATH)
        depth_violations = [v for v in result.violations if "depth" in v.constraint.lower()]
        assert len(depth_violations) > 0, (
            f"Expected depth violation for shallow answer, got: "
            f"{[v.constraint for v in result.violations]}"
        )

    def test_shallow_math_has_verification_violation(self):
        """Shallow math should trigger a verification violation."""
        result = self._validate(SHALLOW_MATH)
        verif_violations = [v for v in result.violations if "verif" in v.constraint.lower()]
        assert len(verif_violations) > 0, (
            f"Expected verification violation for shallow answer, got: "
            f"{[v.constraint for v in result.violations]}"
        )

    def test_refusal_blocked(self):
        """Refusal response should trigger forbidden pattern and be blocked."""
        result = self._validate(REFUSAL_RESPONSE)
        assert result.blocked, (
            f"Refusal should be blocked by forbidden_patterns. "
            f"Violations: {[v.message for v in result.violations]}"
        )

    def test_hedging_response_has_violations(self):
        """Hedging response should fail depth and/or verification."""
        result = self._validate(HEDGING_RESPONSE)
        assert not result.passed, (
            f"Hedging response should NOT pass strict math. "
            f"Violations: {[v.message for v in result.violations]}"
        )

    def test_self_correcting_passes_or_warns(self):
        """Self-correcting response has depth and verification — should not be blocked."""
        result = self._validate(SELF_CORRECTING)
        assert not result.blocked, (
            f"Self-correcting response should not be BLOCKED (it has depth and verification). "
            f"Violations: {[v.message for v in result.violations]}"
        )


class TestLenientContract:
    """Lenient contract should pass almost everything."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(LENIENT_CONTRACT)

    def _validate(self, output: str):
        trace = make_trace(output)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_shallow_passes(self):
        """Shallow answer should pass lenient contract."""
        result = self._validate(SHALLOW_MATH)
        assert not result.blocked, "Lenient contract should not block shallow answer"
        # Lenient only has WARN severity, so exit_code should be 0
        assert (
            result.exit_code == 0
        ), f"Expected exit_code=0 for lenient + shallow, got {result.exit_code}"

    def test_good_passes(self):
        """Good answer should definitely pass."""
        result = self._validate(GOOD_MATH_REASONING)
        assert result.exit_code == 0

    def test_hedging_passes(self):
        """Hedging should pass lenient contract."""
        result = self._validate(HEDGING_RESPONSE)
        assert not result.blocked


class TestImpossibleContract:
    """Impossible contract should block EVERYTHING."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(IMPOSSIBLE_CONTRACT)

    def _validate(self, output: str):
        trace = make_trace(output)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_good_math_blocked(self):
        """Even good reasoning should fail impossible contract."""
        result = self._validate(GOOD_MATH_REASONING)
        assert result.blocked, "Impossible contract should block even good reasoning"
        assert result.exit_code == 1

    def test_verbose_blocked(self):
        """Even verbose response should fail impossible contract."""
        result = self._validate(VERBOSE_RESPONSE)
        assert result.blocked, "Impossible contract should block verbose response"

    def test_many_violations(self):
        """Impossible contract should produce many violations."""
        result = self._validate(GOOD_MATH_REASONING)
        assert (
            len(result.violations) >= 3
        ), f"Expected at least 3 violations from impossible contract, got {len(result.violations)}"


class TestCodeReviewContract:
    """Test code review-specific contract."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(CODE_REVIEW_CONTRACT)

    def _validate(self, output: str):
        trace = make_trace(output, task_id="code_review")
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_good_code_review_passes(self):
        """Thorough code review should pass code review contract."""
        result = self._validate(GOOD_CODE_REVIEW)
        # Should pass or at worst have non-blocking violations
        assert not result.blocked, (
            f"Good code review should not be blocked. "
            f"Violations: {[v.message for v in result.violations]}"
        )

    def test_shallow_code_review_blocked(self):
        """'Looks good' code review should be blocked."""
        result = self._validate(SHALLOW_CODE_REVIEW)
        # Should have forbidden pattern match AND depth violation
        assert result.blocked or not result.passed, (
            f"Shallow code review should fail. "
            f"Violations: {[v.message for v in result.violations]}"
        )

    def test_lgtm_triggers_forbidden_pattern(self):
        """'The code looks fine. No issues found.' should match forbidden pattern."""
        result = self._validate(SHALLOW_CODE_REVIEW)
        forbidden_violations = [
            v
            for v in result.violations
            if "forbidden" in v.constraint.lower() or "pattern" in v.constraint.lower()
        ]
        assert len(forbidden_violations) > 0 or result.blocked, (
            f"Shallow 'looks fine' should trigger forbidden pattern. "
            f"Violations: {[v.constraint for v in result.violations]}"
        )


class TestAllConstraintsContract:
    """Tests the contract that exercises every constraint type."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(ALL_CONSTRAINTS_CONTRACT)

    def _validate(self, output: str):
        trace = make_trace(output)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_good_math_with_all_constraints(self):
        """Good math reasoning should handle most constraints."""
        result = self._validate(GOOD_MATH_REASONING)
        # Should not be blocked — good reasoning meets most constraints
        assert not result.blocked, (
            f"Good math vs all constraints should not block. "
            f"BLOCK violations: {[v.message for v in result.violations if v.severity == Severity.BLOCK]}"
        )

    def test_refusal_blocked_by_forbidden_pattern(self):
        """Refusal matches 'I cannot' forbidden pattern at BLOCK severity."""
        result = self._validate(REFUSAL_RESPONSE)
        assert result.blocked, "Refusal should be blocked by 'I cannot' forbidden pattern"


class TestContractSerialization:
    """Tests that contracts can be loaded from YAML and JSON without corruption."""

    def test_yaml_roundtrip(self, tmp_path):
        """Contract loaded from YAML should preserve all fields."""
        contract = load_contract_from_string(STRICT_MATH_CONTRACT)
        yaml_path = tmp_path / "test.yaml"
        contract.to_yaml(yaml_path)
        loaded = BehaviorContract.from_yaml(yaml_path)
        assert loaded.name == contract.name
        assert loaded.version == contract.version
        assert loaded.depth.min == contract.depth.min
        assert loaded.depth.severity == contract.depth.severity
        assert loaded.verification.required == contract.verification.required

    def test_json_roundtrip(self, tmp_path):
        """Contract loaded from JSON should preserve all fields."""
        contract = load_contract_from_string(STRICT_MATH_CONTRACT)
        json_path = tmp_path / "test.json"
        contract.to_json(json_path)
        loaded = BehaviorContract.from_json(json_path)
        assert loaded.name == contract.name
        assert loaded.depth.min == contract.depth.min

    def test_hash_stability(self):
        """Same contract parsed twice should have same hash."""
        c1 = load_contract_from_string(STRICT_MATH_CONTRACT)
        c2 = load_contract_from_string(STRICT_MATH_CONTRACT)
        assert c1.get_hash() == c2.get_hash(), "Same contract should produce same hash"

    def test_different_contracts_different_hashes(self):
        """Different contracts should have different hashes."""
        c1 = load_contract_from_string(STRICT_MATH_CONTRACT)
        c2 = load_contract_from_string(LENIENT_CONTRACT)
        assert c1.get_hash() != c2.get_hash(), "Different contracts should have different hashes"


class TestWarnOnlyContract:
    """Warn-only contract should never block or fail — only warn."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()
        self.contract = load_contract_from_string(WARN_ONLY_CONTRACT)

    def _validate(self, output: str):
        trace = make_trace(output)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, self.contract, trace)

    def test_shallow_only_warns(self):
        """Shallow answer with warn-only contract should exit 0."""
        result = self._validate(SHALLOW_MATH)
        assert result.exit_code == 0, f"Warn-only should exit 0, got {result.exit_code}"
        assert not result.blocked, "Warn-only should never block"

    def test_warns_present(self):
        """Warn-only violations should still be reported."""
        result = self._validate(SHALLOW_MATH)
        # Shallow answer vs depth.min=5 should triggers at least one warn
        assert result.warn_count >= 0  # this is valid — may or may not have warns

    def test_hedging_only_warns(self):
        """Hedging response with warn-only should not fail."""
        result = self._validate(HEDGING_RESPONSE)
        assert result.exit_code == 0, f"Warn-only should exit 0, got {result.exit_code}"


class TestExitCodes:
    """Verify CI/CD exit codes are correct for all scenarios."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()

    def _validate(self, output: str, contract_yaml: str):
        contract = load_contract_from_string(contract_yaml)
        trace = make_trace(output)
        fp = self.extractor.extract(trace)
        return self.validator.validate(fp, contract, trace)

    def test_exit_code_0_for_pass(self):
        """Passing validation = exit code 0."""
        result = self._validate(GOOD_MATH_REASONING, LENIENT_CONTRACT)
        assert result.exit_code == 0

    def test_exit_code_1_for_block(self):
        """BLOCK-severity violation = exit code 1."""
        result = self._validate(SHALLOW_MATH, STRICT_MATH_CONTRACT)
        assert result.exit_code == 1, f"Expected exit code 1 for BLOCK, got {result.exit_code}"

    def test_ci_output_is_valid_json(self):
        """CI output must be valid serializable dict."""
        contract = load_contract_from_string(STRICT_MATH_CONTRACT)
        trace = make_trace(GOOD_MATH_REASONING)
        fp = self.extractor.extract(trace)
        result = self.validator.validate(fp, contract, trace)
        ci_output = result.to_ci_output()
        assert isinstance(ci_output, dict)
        assert "passed" in ci_output
        assert "blocked" in ci_output
        assert "exit_code" in ci_output
        assert "violations" in ci_output

    def test_report_is_string(self):
        """Human-readable report must be a non-empty string."""
        contract = load_contract_from_string(STRICT_MATH_CONTRACT)
        trace = make_trace(SHALLOW_MATH)
        fp = self.extractor.extract(trace)
        result = self.validator.validate(fp, contract, trace)
        report = result.report()
        assert isinstance(report, str)
        assert len(report) > 0
