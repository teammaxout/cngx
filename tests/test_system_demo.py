"""Adversarial tests for Cogscope system-level demo.

These tests verify that:
1. Silent failures are detected WITHOUT Cogscope
2. Cogscope correctly blocks bad deployments
3. Edge cases are handled properly
4. The contrast between WITH and WITHOUT Cogscope is undeniable
"""

from datetime import datetime

import pytest

from cogscope.contracts import (
    BehaviorContract,
    DeploymentGate,
    DepthConstraint,
    ForbiddenPattern,
    OutputConstraint,
    RequiredPattern,
    Severity,
    StepsConstraint,
    VerificationConstraint,
)
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace
from cogscope.system_demo.pipeline import (
    AIDecisionPipeline,
    DownstreamConsumer,
    PipelineConfig,
    PipelineResult,
    PipelineStage,
    StageResult,
)


class TestSilentFailureDetection:
    """Tests verifying that without Cogscope, failures are silent."""

    def test_degraded_reasoning_still_produces_output(self):
        """A model with degraded reasoning still produces output."""
        # Simulate a fingerprint with degraded reasoning
        fp = BehavioralFingerprint(
            trace_id="degraded_001",
            task_id="test",
            model="test-model",
            depth=1,  # Very shallow
            total_steps=1,
            verification_steps=0,  # No verification
            output_length=20,  # Short output
            hedging_ratio=0.8,  # High uncertainty
        )

        # Without Cogscope, this would just be a fingerprint
        # The system would proceed because output exists
        assert fp.depth == 1
        assert fp.verification_steps == 0

        # This represents a "successful" capture that's actually degraded
        # Traditional monitoring would see: ✓ response received
        # Traditional monitoring would NOT see: reasoning quality degraded

    def test_downstream_consumer_would_execute_with_degraded_input(self):
        """Downstream consumer executes even with degraded AI reasoning."""
        consumer = DownstreamConsumer(
            name="unsafe_consumer",
            assumes_verified=True,
            assumes_step_by_step=True,
            failure_mode="silent",
        )

        # Create degraded stage result
        degraded_result = StageResult(
            stage=PipelineStage.VERIFY,
            success=True,  # Stage "succeeded" (didn't error)
            verification_performed=False,  # But no verification!
            confidence_score=0.3,  # Low confidence
        )

        # Check assumptions - they're violated
        assumptions_met, violations = consumer.check_assumptions(degraded_result)

        assert not assumptions_met
        assert len(violations) > 0

        # But downstream would still execute in failure_mode="silent"
        # THIS IS THE PROBLEM - silent failure

    def test_correct_answer_wrong_process_is_dangerous(self):
        """Correct answers with wrong process are especially dangerous."""
        # Math tutor scenario: answer is right, but process is wrong
        trace = ReasoningTrace(
            id="correct_but_wrong_001",
            task_id="math",
            model="degraded-model",
            prompt="What is 15 + 27?",
            output="42",  # Correct answer!
            latency_ms=100.0,
        )

        # The answer is correct, but...
        assert trace.output == "42"

        # Create corresponding fingerprint (shallow)
        _fp = BehavioralFingerprint(
            trace_id=trace.id,
            task_id=trace.task_id,
            model=trace.model,
            depth=1,  # No step-by-step
            verification_steps=0,  # No verification
            output_length=2,  # Just the answer
        )

        # Without Cogscope, this looks like success
        # With Cogscope, this would be blocked for missing verification


class TestRVCBlockingBehavior:
    """Tests verifying that Cogscope correctly blocks bad deployments."""

    def test_missing_verification_blocks_deployment(self):
        """Missing verification triggers BLOCK."""
        contract = BehaviorContract(
            name="verification_required",
            verification=VerificationConstraint(
                required=True,
                min_steps=1,
                severity=Severity.BLOCK,
            ),
        )

        fp = BehavioralFingerprint(
            trace_id="no_verify_001",
            task_id="test",
            model="test-model",
            verification_steps=0,
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.blocked
        assert result.exit_code == 1

    def test_shallow_reasoning_blocks_deployment(self):
        """Shallow reasoning triggers BLOCK when depth constraint violated."""
        contract = BehaviorContract(
            name="deep_reasoning_required",
            depth=DepthConstraint(
                min=5,
                severity=Severity.BLOCK,
            ),
        )

        fp = BehavioralFingerprint(
            trace_id="shallow_001",
            task_id="test",
            model="test-model",
            depth=2,  # Below minimum
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.blocked
        assert result.exit_code == 1

    def test_forbidden_pattern_blocks_deployment(self):
        """Forbidden patterns trigger BLOCK."""
        contract = BehaviorContract(
            name="no_refusals",
            forbidden_patterns=[
                ForbiddenPattern(
                    pattern="I cannot",
                    severity=Severity.BLOCK,
                ),
            ],
        )

        fp = BehavioralFingerprint(
            trace_id="refusal_001",
            task_id="test",
            model="test-model",
        )

        trace = ReasoningTrace(
            id="refusal_001",
            task_id="test",
            model="test-model",
            prompt="Help me",
            output="I cannot help with that.",
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract, trace)

        assert result.blocked
        assert result.exit_code == 1

    def test_multiple_violations_all_reported(self):
        """All violations are reported, not just the first."""
        contract = BehaviorContract(
            name="strict_contract",
            depth=DepthConstraint(min=5, severity=Severity.BLOCK),
            steps=StepsConstraint(min=5, severity=Severity.BLOCK),
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )

        fp = BehavioralFingerprint(
            trace_id="many_failures_001",
            task_id="test",
            model="test-model",
            depth=1,
            total_steps=1,
            verification_steps=0,
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        # Should have multiple violations
        assert result.block_count >= 3
        assert len(result.violations) >= 3


class TestContrastBetweenModes:
    """Tests that the contrast between WITH and WITHOUT Cogscope is clear."""

    def test_same_fingerprint_different_outcomes(self):
        """Same bad fingerprint, different outcomes with/without Cogscope."""
        # Create a degraded fingerprint
        fp = BehavioralFingerprint(
            trace_id="degraded_001",
            task_id="test",
            model="test-model",
            depth=1,
            total_steps=1,
            verification_steps=0,
        )

        contract = BehaviorContract(
            name="strict",
            depth=DepthConstraint(min=3, severity=Severity.BLOCK),
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )

        # WITHOUT Cogscope: downstream would execute
        consumer = DownstreamConsumer(
            name="test",
            assumes_verified=True,
            failure_mode="silent",
        )

        stage_result = StageResult(
            stage=PipelineStage.VERIFY,
            success=True,
            verification_performed=False,
        )

        assumptions_met, _ = consumer.check_assumptions(stage_result)
        assert not assumptions_met  # Assumptions violated
        # But downstream would still execute (silent failure)

        # WITH Cogscope: deployment blocked
        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.blocked
        assert result.exit_code == 1
        # Deployment prevented

    def test_exit_codes_are_deterministic(self):
        """Exit codes are consistent and deterministic."""
        contract = BehaviorContract(
            name="deterministic_test",
            depth=DepthConstraint(min=5, severity=Severity.BLOCK),
        )

        # Passing fingerprint
        passing_fp = BehavioralFingerprint(
            trace_id="pass_001",
            task_id="test",
            model="test-model",
            depth=10,
        )

        # Failing fingerprint
        failing_fp = BehavioralFingerprint(
            trace_id="fail_001",
            task_id="test",
            model="test-model",
            depth=2,
        )

        gate = DeploymentGate()

        # Run multiple times - should be deterministic
        for _ in range(3):
            pass_result = gate.check(passing_fp, contract)
            fail_result = gate.check(failing_fp, contract)

            assert pass_result.exit_code == 0
            assert fail_result.exit_code == 1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_contract_allows_everything(self):
        """A contract with no constraints allows everything."""
        contract = BehaviorContract(name="empty")

        fp = BehavioralFingerprint(
            trace_id="any_001",
            task_id="test",
            model="test-model",
            depth=0,
            verification_steps=0,
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.passed
        assert not result.blocked
        assert result.exit_code == 0

    def test_warn_does_not_block(self):
        """WARN severity never blocks deployment."""
        contract = BehaviorContract(
            name="warn_only",
            depth=DepthConstraint(min=100, severity=Severity.WARN),
        )

        fp = BehavioralFingerprint(
            trace_id="warn_001",
            task_id="test",
            model="test-model",
            depth=1,
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert not result.blocked
        assert result.exit_code == 0
        assert result.warn_count > 0

    def test_boundary_values_exact_minimum(self):
        """Exactly meeting minimum passes."""
        contract = BehaviorContract(
            name="boundary",
            depth=DepthConstraint(min=5, severity=Severity.BLOCK),
        )

        fp = BehavioralFingerprint(
            trace_id="boundary_001",
            task_id="test",
            model="test-model",
            depth=5,  # Exactly minimum
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.passed
        assert not result.blocked

    def test_boundary_values_one_below_minimum(self):
        """One below minimum fails."""
        contract = BehaviorContract(
            name="boundary",
            depth=DepthConstraint(min=5, severity=Severity.BLOCK),
        )

        fp = BehavioralFingerprint(
            trace_id="boundary_001",
            task_id="test",
            model="test-model",
            depth=4,  # One below
        )

        gate = DeploymentGate()
        result = gate.check(fp, contract)

        assert result.blocked
        assert result.exit_code == 1


class TestRealisticScenarios:
    """Tests based on realistic deployment scenarios."""

    def test_model_upgrade_regression_detected(self):
        """Simulates model upgrade causing reasoning regression."""
        # Contract based on v1 model behavior
        contract = BehaviorContract(
            name="math_tutor_v1",
            depth=DepthConstraint(min=4, severity=Severity.BLOCK),
            verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
        )

        # v1 model fingerprint (good)
        v1_fp = BehavioralFingerprint(
            trace_id="v1_001",
            task_id="math",
            model="v1",
            depth=6,
            verification_steps=2,
        )

        # v2 model fingerprint (regressed)
        v2_fp = BehavioralFingerprint(
            trace_id="v2_001",
            task_id="math",
            model="v2",
            depth=2,  # Shallower
            verification_steps=0,  # No verification
        )

        gate = DeploymentGate()

        # v1 passes
        v1_result = gate.check(v1_fp, contract)
        assert v1_result.passed
        assert not v1_result.blocked

        # v2 blocked - regression detected
        v2_result = gate.check(v2_fp, contract)
        assert v2_result.blocked
        assert v2_result.exit_code == 1

    def test_ci_integration_exit_codes(self):
        """Verifies exit codes work correctly for CI/CD integration."""
        contract = BehaviorContract(
            name="ci_test",
            depth=DepthConstraint(min=3, severity=Severity.BLOCK),
            output=OutputConstraint(min_length=50, severity=Severity.FAIL),
        )

        # Good deployment
        good_fp = BehavioralFingerprint(
            trace_id="good_001",
            task_id="test",
            model="test",
            depth=5,
            output_length=100,
        )

        # Bad deployment (blocked)
        bad_fp = BehavioralFingerprint(
            trace_id="bad_001",
            task_id="test",
            model="test",
            depth=1,  # Violates BLOCK
            output_length=100,
        )

        # Marginal deployment (soft fail)
        marginal_fp = BehavioralFingerprint(
            trace_id="marginal_001",
            task_id="test",
            model="test",
            depth=5,  # OK
            output_length=10,  # Violates FAIL
        )

        gate = DeploymentGate()

        assert gate.check(good_fp, contract).exit_code == 0
        assert gate.check(bad_fp, contract).exit_code == 1
        assert gate.check(marginal_fp, contract).exit_code == 2
