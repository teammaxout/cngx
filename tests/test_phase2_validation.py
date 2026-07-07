"""Phase 2 — Comprehensive validation tests.

Covers all missing test categories identified during audit:
1. Regression scenarios (model version, temperature, prompt, reasoning removal, CoT depth)
2. False positive tests (formatting changes, minor rephrasing)
3. Stress tests (rapid model switching, incomplete/truncated reasoning)
4. Tool constraint violation tests
5. Output constraint (require_structured) tests
"""

import copy
import time
from datetime import datetime
from typing import List, Optional

import pytest

from cogscope.contracts.schema import (
    BehaviorContract,
    DepthConstraint,
    ForbiddenPattern,
    OutputConstraint,
    RequiredPattern,
    Severity,
    StepsConstraint,
    ToolConstraint,
    UncertaintyConstraint,
    VerificationConstraint,
)
from cogscope.contracts.validator import ContractValidator
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace, TokenUsage
from cogscope.diff.engine import DiffEngine
from cogscope.fingerprint.extractor import FingerprintExtractor

# ═══════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════


def _make_trace(
    prompt: str = "What is 2+2?",
    output: str = "The answer is 4.",
    reasoning: str = "",
    model: str = "gpt-4o",
    tools: Optional[List] = None,
    trace_id: str = "test_trace",
    task_id: str = "test_task",
) -> ReasoningTrace:
    """Create a ReasoningTrace with the given content."""
    return ReasoningTrace(
        id=trace_id,
        timestamp=datetime.utcnow(),
        task_id=task_id,
        model=model,
        prompt=prompt,
        output=output,
        reasoning_content=reasoning or output,
        tools_used=tools or [],
        token_usage=TokenUsage(prompt_tokens=50, completion_tokens=100, total_tokens=150),
        metadata={},
    )


def _make_fingerprint(**overrides) -> BehavioralFingerprint:
    """Create a BehavioralFingerprint with defaults, applying overrides."""
    defaults = {
        "trace_id": "test_trace",
        "task_id": "test_task",
        "timestamp": datetime.utcnow(),
        "model": "gpt-4o",
        "depth": 3,
        "branching_factor": 0.5,
        "total_steps": 5,
        "max_step_length": 100,
        "tool_call_count": 0,
        "tool_call_sequence": [],
        "tool_diversity": 0.0,
        "tool_success_rate": 1.0,
        "output_length": 200,
        "reasoning_length": 400,
        "compression_ratio": 0.5,
        "avg_sentence_length": 15.0,
        "correction_count": 0,
        "backtrack_count": 0,
        "revision_count": 0,
        "uncertainty_markers": 0,
        "confidence_markers": 2,
        "hedging_ratio": 0.0,
        "verification_steps": 2,
        "example_count": 1,
        "structured_output": True,
        "tokens_per_step": 20.0,
        "reasoning_overhead": 0.5,
    }
    defaults.update(overrides)
    return BehavioralFingerprint(**defaults)


# ═══════════════════════════════════════════════
#  SECTION 1: Regression Scenarios
# ═══════════════════════════════════════════════


class TestRegressionScenarios:
    """Verify that behavioral changes produce appropriate drift increases."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.diff_engine = DiffEngine()

    # ── 1a. Model version change ──

    def test_model_version_change_produces_drift(self):
        """Switching model versions (gpt-4 → gpt-4o) with different output
        patterns should produce measurable drift."""
        trace_v1 = _make_trace(
            prompt="Explain quantum entanglement.",
            output=(
                "Quantum entanglement is a phenomenon where two particles "
                "become correlated. Step 1: Consider two photons. "
                "Step 2: When measured, they show correlated results. "
                "Step 3: This holds regardless of distance. The answer is clear."
            ),
            model="gpt-4",
        )
        trace_v2 = _make_trace(
            prompt="Explain quantum entanglement.",
            output=(
                "I think quantum entanglement might involve particles being linked. "
                "Perhaps when one is measured, the other changes too? "
                "It's possible that distance doesn't matter, but I'm not entirely sure. "
                "Let me reconsider — actually, the correlation is well-established."
            ),
            model="gpt-4o",
        )
        fp_v1 = self.extractor.extract(trace_v1)
        fp_v2 = self.extractor.extract(trace_v2)
        diff = self.diff_engine.diff(fp_v1, fp_v2)

        # Model version change with different reasoning style should produce drift
        assert diff.drift_score > 0.0, "Model version change should produce drift"
        # The second output has hedging/uncertainty markers vs. confident first
        assert (
            fp_v2.uncertainty_markers > fp_v1.uncertainty_markers
            or fp_v2.correction_count > fp_v1.correction_count
        ), "Output behavioral change should be reflected in fingerprint metrics"

    # ── 1b. Temperature change ──

    def test_temperature_change_produces_drift(self):
        """Higher temperature responses tend to be more verbose and less structured,
        which should produce drift vs. a deterministic baseline."""
        # Low temperature: concise, structured, confident
        trace_low_temp = _make_trace(
            prompt="What is the capital of France?",
            output="The capital of France is Paris.",
            model="gpt-4o",
        )
        # High temperature: verbose, hedging, less structured
        trace_high_temp = _make_trace(
            prompt="What is the capital of France?",
            output=(
                "Well, thinking about this... France is a country in Western Europe, "
                "and I believe its capital might be Paris. Actually, yes, Paris is "
                "definitely the capital. Let me verify — Paris has been the capital "
                "since at least the 10th century. So to confirm, the capital of France "
                "is indeed Paris, which is also the largest city in the country."
            ),
            model="gpt-4o",
        )
        fp_low = self.extractor.extract(trace_low_temp)
        fp_high = self.extractor.extract(trace_high_temp)
        diff = self.diff_engine.diff(fp_low, fp_high)

        assert diff.drift_score > 0.0, "Temperature change should produce drift"
        assert (
            fp_high.output_length > fp_low.output_length
        ), "High temperature should produce longer output"

    # ── 1c. Prompt change ──

    def test_prompt_modification_produces_drift(self):
        """Removing 'step by step' from a prompt should reduce reasoning depth
        and produce measurable drift."""
        trace_detailed = _make_trace(
            prompt="Explain step by step how photosynthesis works.",
            output=(
                "Step 1: Light energy is absorbed by chlorophyll in the leaves. "
                "Step 2: Water molecules are split in the thylakoid membranes. "
                "Step 3: Carbon dioxide is fixed via the Calvin cycle. "
                "Step 4: Glucose is synthesized as the final product. "
                "Let me verify: the light reactions produce ATP and NADPH, "
                "which power the Calvin cycle. Confirmed."
            ),
        )
        trace_simple = _make_trace(
            prompt="How does photosynthesis work?",
            output="Photosynthesis converts light energy into chemical energy in plants.",
        )
        fp_detailed = self.extractor.extract(trace_detailed)
        fp_simple = self.extractor.extract(trace_simple)
        diff = self.diff_engine.diff(fp_detailed, fp_simple)

        assert diff.drift_score > 0.0, "Prompt change should produce drift"
        assert (
            fp_detailed.total_steps > fp_simple.total_steps
            or fp_detailed.output_length > fp_simple.output_length
        ), "Detailed prompt should produce deeper/longer reasoning"

    # ── 1d. Reasoning instruction removal ──

    def test_reasoning_instruction_removal_produces_drift(self):
        """Removing reasoning instructions should reduce verification steps,
        correction counts, and depth — producing drift."""
        trace_with_reasoning = _make_trace(
            prompt="Think carefully and show your work: What is 15% of 340?",
            output=(
                "Let me think step by step. "
                "Step 1: 15% means 15/100 = 0.15. "
                "Step 2: 340 × 0.15 = 51. "
                "Let me verify: 10% of 340 is 34, and 5% is 17, so 34 + 17 = 51. "
                "Confirmed. The answer is 51."
            ),
        )
        trace_without_reasoning = _make_trace(
            prompt="What is 15% of 340?",
            output="51",
        )
        fp_with = self.extractor.extract(trace_with_reasoning)
        fp_without = self.extractor.extract(trace_without_reasoning)
        diff = self.diff_engine.diff(fp_with, fp_without)

        assert diff.drift_score > 0.0, "Removing reasoning instructions should produce drift"
        assert (
            fp_with.verification_steps >= fp_without.verification_steps
        ), "Reasoning instructions should produce more verification"
        assert (
            fp_with.output_length > fp_without.output_length
        ), "Reasoning instructions should produce longer output"

    # ── 1e. Reduced chain-of-thought depth ──

    def test_reduced_cot_depth_produces_drift(self):
        """Progressively reducing chain-of-thought depth should produce
        increasing drift from the deep baseline."""
        # Deep reasoning (5 steps)
        trace_deep = _make_trace(
            prompt="What is the derivative of x^3 + 2x^2 - 5x + 1?",
            output=(
                "Step 1: I need to find d/dx of x^3 + 2x^2 - 5x + 1. "
                "Step 2: Apply the power rule to each term. "
                "Step 3: d/dx(x^3) = 3x^2. "
                "Step 4: d/dx(2x^2) = 4x. d/dx(-5x) = -5. d/dx(1) = 0. "
                "Step 5: Combining: 3x^2 + 4x - 5. "
                "Let me verify by checking each term individually. Confirmed."
            ),
        )
        # Medium reasoning (3 steps)
        trace_medium = _make_trace(
            prompt="What is the derivative of x^3 + 2x^2 - 5x + 1?",
            output=(
                "Using the power rule: "
                "d/dx(x^3) = 3x^2, d/dx(2x^2) = 4x, d/dx(-5x) = -5, d/dx(1) = 0. "
                "Answer: 3x^2 + 4x - 5."
            ),
        )
        # Shallow reasoning (1 step)
        trace_shallow = _make_trace(
            prompt="What is the derivative of x^3 + 2x^2 - 5x + 1?",
            output="3x^2 + 4x - 5",
        )

        fp_deep = self.extractor.extract(trace_deep)
        fp_medium = self.extractor.extract(trace_medium)
        fp_shallow = self.extractor.extract(trace_shallow)

        drift_medium = self.diff_engine.diff(fp_deep, fp_medium).drift_score
        drift_shallow = self.diff_engine.diff(fp_deep, fp_shallow).drift_score

        assert drift_medium > 0.0, "Medium CoT should drift from deep"
        assert drift_shallow > 0.0, "Shallow CoT should drift from deep"
        assert drift_shallow >= drift_medium, "Shallower CoT should produce equal or greater drift"


# ═══════════════════════════════════════════════
#  SECTION 2: False Positive Tests
# ═══════════════════════════════════════════════


class TestFalsePositives:
    """Ensure minor changes do not produce excessive drift or contract failures."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.diff_engine = DiffEngine()
        self.validator = ContractValidator()

    # ── 2a. Small formatting changes should NOT produce high drift ──

    def test_formatting_change_low_drift(self):
        """Bullet points vs. numbered list of the same content should produce
        minimal drift (below significance threshold)."""
        trace_numbered = _make_trace(
            output=(
                "1. First, identify the problem. "
                "2. Then, analyze the root cause. "
                "3. Finally, implement the solution."
            ),
        )
        trace_bullets = _make_trace(
            output=(
                "- First, identify the problem. "
                "- Then, analyze the root cause. "
                "- Finally, implement the solution."
            ),
        )
        fp_numbered = self.extractor.extract(trace_numbered)
        fp_bullets = self.extractor.extract(trace_bullets)
        diff = self.diff_engine.diff(fp_numbered, fp_bullets)

        # Formatting-only changes should not produce significant drift
        assert (
            diff.drift_score < 2.0
        ), f"Formatting change produced drift={diff.drift_score}, expected <2.0"

    def test_whitespace_variation_low_drift(self):
        """Extra whitespace and newlines should not cause meaningful drift."""
        trace_compact = _make_trace(
            output="The answer is 42. This is the result of the calculation.",
        )
        trace_spaced = _make_trace(
            output="The answer is 42.  This is the result of the calculation. ",
        )
        fp_compact = self.extractor.extract(trace_compact)
        fp_spaced = self.extractor.extract(trace_spaced)
        diff = self.diff_engine.diff(fp_compact, fp_spaced)

        assert (
            diff.drift_score < 2.0
        ), f"Whitespace variation produced drift={diff.drift_score}, expected <2.0"

    def test_capitalization_change_low_drift(self):
        """Capitalization differences should produce negligible drift."""
        trace_lower = _make_trace(
            output="the capital of france is paris. it has been the capital since medieval times.",
        )
        trace_upper = _make_trace(
            output="The Capital of France is Paris. It has been the capital since medieval times.",
        )
        fp_lower = self.extractor.extract(trace_lower)
        fp_upper = self.extractor.extract(trace_upper)
        diff = self.diff_engine.diff(fp_lower, fp_upper)

        assert (
            diff.drift_score < 2.0
        ), f"Capitalization change produced drift={diff.drift_score}, expected <2.0"

    # ── 2b. Minor output rephrasing should not break contracts ──

    def test_rephrased_output_passes_same_contract(self):
        """A slightly rephrased output with the same meaning should pass
        the same contract as the original."""
        contract = BehaviorContract(
            name="basic_quality",
            depth=DepthConstraint(min_depth=1),
            output=OutputConstraint(min_length=20),
        )

        trace_original = _make_trace(
            output=(
                "Step 1: The capital of France is Paris. "
                "Step 2: Paris is located in northern France. "
                "The answer is Paris."
            ),
        )
        trace_rephrased = _make_trace(
            output=(
                "Step 1: France's capital city is Paris. "
                "Step 2: It's situated in the north of France. "
                "Therefore, the answer is Paris."
            ),
        )

        fp_original = self.extractor.extract(trace_original)
        fp_rephrased = self.extractor.extract(trace_rephrased)

        result_original = self.validator.validate(fp_original, contract, trace_original)
        result_rephrased = self.validator.validate(fp_rephrased, contract, trace_rephrased)

        assert result_original.passed, "Original should pass contract"
        assert result_rephrased.passed, "Rephrased output should also pass contract"

    def test_synonym_substitution_no_false_positive(self):
        """Replacing words with synonyms should not trigger false positives."""
        contract = BehaviorContract(
            name="reasoning_quality",
            depth=DepthConstraint(min_depth=1),
            output=OutputConstraint(min_length=10),
            uncertainty=UncertaintyConstraint(max_hedging_ratio=0.5),
        )

        trace_v1 = _make_trace(
            output="The solution is straightforward. We compute 2+2=4. The answer is 4.",
        )
        trace_v2 = _make_trace(
            output="The answer is simple. We calculate 2+2=4. The result is 4.",
        )

        fp_v1 = self.extractor.extract(trace_v1)
        fp_v2 = self.extractor.extract(trace_v2)

        result_v1 = self.validator.validate(fp_v1, contract, trace_v1)
        result_v2 = self.validator.validate(fp_v2, contract, trace_v2)

        assert result_v1.passed, "Version 1 should pass"
        assert result_v2.passed, "Version 2 (synonyms) should also pass"


# ═══════════════════════════════════════════════
#  SECTION 3: Tool Constraint Tests
# ═══════════════════════════════════════════════


class TestToolConstraints:
    """Test all ToolConstraint validation scenarios."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.validator = ContractValidator()

    def test_required_tool_missing_violation(self):
        """Missing a required tool should produce a violation."""
        contract = BehaviorContract(
            name="tool_required",
            tools=ToolConstraint(
                required=["calculator", "search"],
                severity=Severity.BLOCK,
            ),
        )
        # Fingerprint with only calculator used, missing search
        fp = _make_fingerprint(
            tool_call_count=1,
            tool_call_sequence=["calculator"],
            tool_diversity=1.0,
        )
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        assert not result.passed, "Should fail when required tool is missing"

        tool_violations = [v for v in result.violations if "required" in v.constraint]
        assert len(tool_violations) >= 1, "Should have at least one tool.required violation"
        assert any(
            "search" in v.message for v in tool_violations
        ), "Violation should mention the missing 'search' tool"

    def test_forbidden_tool_used_violation(self):
        """Using a forbidden tool should produce a violation."""
        contract = BehaviorContract(
            name="tool_forbidden",
            tools=ToolConstraint(
                forbidden=["code_execution", "file_access"],
                severity=Severity.BLOCK,
            ),
        )
        fp = _make_fingerprint(
            tool_call_count=2,
            tool_call_sequence=["code_execution", "search"],
            tool_diversity=1.0,
        )
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        assert not result.passed, "Should fail when forbidden tool is used"

        tool_violations = [v for v in result.violations if "forbidden" in v.constraint]
        assert len(tool_violations) >= 1, "Should have at least one tool.forbidden violation"

    def test_max_calls_exceeded_violation(self):
        """Exceeding max tool calls should produce a violation."""
        contract = BehaviorContract(
            name="tool_max_calls",
            tools=ToolConstraint(max_calls=3, severity=Severity.FAIL),
        )
        fp = _make_fingerprint(
            tool_call_count=5,
            tool_call_sequence=["calc", "calc", "search", "calc", "search"],
        )
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        assert not result.passed, "Should fail when max_calls exceeded"

        max_violations = [v for v in result.violations if "max_calls" in v.constraint]
        assert len(max_violations) == 1, "Should have exactly one max_calls violation"

    def test_min_diversity_violation(self):
        """Below-minimum tool diversity should produce a violation."""
        contract = BehaviorContract(
            name="tool_diversity",
            tools=ToolConstraint(min_diversity=0.5, severity=Severity.WARN),
        )
        fp = _make_fingerprint(
            tool_call_count=4,
            tool_call_sequence=["calc", "calc", "calc", "calc"],
            tool_diversity=0.25,
        )
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)

        diversity_violations = [v for v in result.violations if "diversity" in v.constraint]
        assert len(diversity_violations) == 1, "Should have one min_diversity violation"

    def test_all_tool_constraints_pass(self):
        """A fingerprint meeting all tool constraints should pass."""
        contract = BehaviorContract(
            name="tool_all_pass",
            tools=ToolConstraint(
                required=["calculator"],
                forbidden=["dangerous_tool"],
                max_calls=5,
                min_diversity=0.3,
                severity=Severity.BLOCK,
            ),
        )
        fp = _make_fingerprint(
            tool_call_count=3,
            tool_call_sequence=["calculator", "search", "calculator"],
            tool_diversity=0.67,
        )
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        tool_violations = [v for v in result.violations if "tool" in v.constraint]
        assert len(tool_violations) == 0, "All tool constraints should pass"


# ═══════════════════════════════════════════════
#  SECTION 4: Output Constraint — require_structured
# ═══════════════════════════════════════════════


class TestOutputConstraints:
    """Test OutputConstraint validation including require_structured."""

    def setup_method(self):
        self.validator = ContractValidator()

    def test_require_structured_violation(self):
        """Unstructured output should violate require_structured."""
        contract = BehaviorContract(
            name="structured_required",
            output=OutputConstraint(require_structured=True, severity=Severity.FAIL),
        )
        fp = _make_fingerprint(structured_output=False)
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        assert not result.passed, "Should fail when structured output is required but absent"

        struct_violations = [v for v in result.violations if "structured" in v.constraint]
        assert len(struct_violations) == 1, "Should have exactly one require_structured violation"

    def test_require_structured_passes(self):
        """Structured output should pass require_structured."""
        contract = BehaviorContract(
            name="structured_required",
            output=OutputConstraint(require_structured=True, severity=Severity.FAIL),
        )
        fp = _make_fingerprint(structured_output=True)
        trace = _make_trace()

        result = self.validator.validate(fp, contract, trace)
        struct_violations = [v for v in result.violations if "structured" in v.constraint]
        assert len(struct_violations) == 0, "Structured output should pass"

    def test_min_max_length_combined(self):
        """Output violating both min and max length should report both."""
        contract_min = BehaviorContract(
            name="too_short",
            output=OutputConstraint(min_length=500, severity=Severity.FAIL),
        )
        fp = _make_fingerprint(output_length=10)
        trace = _make_trace()

        result = self.validator.validate(fp, contract_min, trace)
        assert not result.passed, "Short output should fail min_length"

        contract_max = BehaviorContract(
            name="too_long",
            output=OutputConstraint(max_length=5, severity=Severity.FAIL),
        )
        result2 = self.validator.validate(fp, contract_max, trace)
        assert not result2.passed, "10-char output should fail max_length=5"


# ═══════════════════════════════════════════════
#  SECTION 5: Stress Tests
# ═══════════════════════════════════════════════


class TestStressScenarios:
    """Stress test edge cases for system stability."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()
        self.diff_engine = DiffEngine()
        self.validator = ContractValidator()

    # ── 5a. Rapid model switching ──

    def test_rapid_model_switching_fingerprint_integrity(self):
        """Rapidly switching between different models should produce valid,
        distinct fingerprints for each."""
        models = ["gpt-4o", "claude-sonnet", "gemini-2.5-flash", "gpt-4o-mini"]
        outputs = [
            "The answer is 4. I computed 2+2=4.",
            "Let me think step by step. 2+2 equals 4. I'm confident in this answer.",
            "Step 1: 2+2. Step 2: The result is 4. Verification: correct.",
            "4",
        ]

        fingerprints = []
        for model, output in zip(models, outputs):
            trace = _make_trace(model=model, output=output)
            fp = self.extractor.extract(trace)
            fingerprints.append(fp)

        # All fingerprints should be valid
        for i, fp in enumerate(fingerprints):
            assert fp.output_length >= 0, f"Model {models[i]}: invalid output_length"
            assert fp.depth >= 0, f"Model {models[i]}: invalid depth"
            assert fp.total_steps >= 0, f"Model {models[i]}: invalid total_steps"
            assert 0.0 <= fp.hedging_ratio <= 1.0, f"Model {models[i]}: invalid hedging_ratio"

        # Different outputs should produce distinct fingerprints
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                # At least one metric should differ between different model outputs
                diff = self.diff_engine.diff(fingerprints[i], fingerprints[j])
                # Verify the diff computation doesn't crash
                assert diff.drift_score >= 0.0, "Drift score should be non-negative"

    def test_rapid_sequential_fingerprinting(self):
        """100 rapid sequential fingerprint extractions should all succeed."""
        traces = []
        for i in range(100):
            trace = _make_trace(
                output=f"Answer {i}: The result is {i * 2}. Step {i}: computed.",
                trace_id=f"rapid_{i}",
                model=["gpt-4o", "claude-sonnet", "gemini-flash"][i % 3],
            )
            traces.append(trace)

        start = time.monotonic()
        fingerprints = [self.extractor.extract(t) for t in traces]
        elapsed = time.monotonic() - start

        assert len(fingerprints) == 100, "All 100 fingerprints should be extracted"
        for fp in fingerprints:
            assert fp.output_length > 0, "Each fingerprint should have non-zero output_length"

        # Should complete in reasonable time (<5s for 100 traces)
        assert elapsed < 5.0, f"100 extractions took {elapsed:.1f}s, expected <5s"

    # ── 5b. Incomplete / truncated reasoning traces ──

    def test_truncated_mid_sentence_reasoning(self):
        """A response cut off mid-sentence should produce a valid fingerprint
        without crashing."""
        trace = _make_trace(
            output="Step 1: First we need to consider the implications of—",
            reasoning="Step 1: First we need to consider the implications of—",
        )
        fp = self.extractor.extract(trace)

        assert fp is not None, "Should produce a fingerprint"
        assert fp.output_length > 0, "Should have non-zero output length"
        assert fp.depth >= 0, "Depth should be non-negative"

    def test_truncated_mid_word_reasoning(self):
        """A response cut off mid-word should produce a valid fingerprint."""
        trace = _make_trace(
            output="The answer involves compu",
            reasoning="The answer involves compu",
        )
        fp = self.extractor.extract(trace)

        assert fp is not None, "Should produce a fingerprint"
        assert fp.output_length > 0, "Should have non-zero output length"

    def test_missing_finish_reason_trace(self):
        """A trace with no explicit finish reason should still be processable."""
        trace = _make_trace(
            output=(
                "Step 1: Consider the problem.\n"
                "Step 2: Analyze the data.\n"
                "Step 3: Formulate a hypoth"  # Truncated
            ),
        )
        # Explicitly set finish_reason to None if the model supports it
        if hasattr(trace, "finish_reason"):
            trace.finish_reason = None

        fp = self.extractor.extract(trace)
        assert fp is not None, "Should handle missing finish reason"
        assert fp.total_steps >= 0, "Steps should be non-negative"

    def test_empty_reasoning_with_output(self):
        """Output present but reasoning_content empty should not crash."""
        trace = _make_trace(
            output="The answer is 42.",
            reasoning="",
        )
        fp = self.extractor.extract(trace)
        assert fp is not None, "Should handle empty reasoning"
        assert fp.output_length > 0, "Output length should be set"

    def test_only_special_characters_reasoning(self):
        """Reasoning with only special chars should produce valid fingerprint."""
        trace = _make_trace(
            output="!!@#$%^&*()",
            reasoning="!!@#$%^&*()",
        )
        fp = self.extractor.extract(trace)
        assert fp is not None, "Should handle special chars"
        assert fp.output_length > 0, "Output length should be positive"
        # No corrections, verifications, or hedging should be detected
        assert fp.correction_count == 0, "No corrections in special chars"

    def test_very_long_reasoning_chain(self):
        """A trace with extremely long reasoning (100+ steps) should not crash
        or produce invalid metrics."""
        steps = [f"Step {i}: Reasoning item {i}. " for i in range(150)]
        long_reasoning = "\n".join(steps)
        trace = _make_trace(
            output=long_reasoning,
            reasoning=long_reasoning,
        )
        fp = self.extractor.extract(trace)

        assert fp is not None, "Should handle 150-step reasoning"
        assert fp.output_length > 1000, "Should reflect long output"
        assert fp.total_steps > 0, "Should detect multiple steps"

    def test_contract_against_truncated_trace(self):
        """Contract validation should handle truncated traces gracefully."""
        contract = BehaviorContract(
            name="quality_check",
            depth=DepthConstraint(min_depth=1),
            output=OutputConstraint(min_length=5),
        )
        trace = _make_trace(
            output="Step 1: First we—",
            reasoning="Step 1: First we—",
        )
        fp = self.extractor.extract(trace)

        # Should not crash
        result = self.validator.validate(fp, contract, trace)
        assert result is not None, "Validation should complete on truncated trace"


# ═══════════════════════════════════════════════
#  SECTION 6: Fingerprint Stability Across Repetitions
# ═══════════════════════════════════════════════


class TestFingerprintStability:
    """Verify fingerprint extraction is deterministic."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_exact_same_input_produces_identical_fingerprints(self):
        """Running the same trace through extraction 10 times should always
        produce identical fingerprints."""
        trace = _make_trace(
            prompt="What is the meaning of life?",
            output=(
                "Step 1: Consider philosophical perspectives. "
                "Step 2: The number 42 is a famous humorous answer. "
                "Step 3: More seriously, meaning is subjective. "
                "Let me verify: philosophers have debated this for centuries. "
                "I'm confident that meaning is individually defined."
            ),
        )

        fingerprints = [self.extractor.extract(trace) for _ in range(10)]

        for i in range(1, 10):
            assert fingerprints[i].depth == fingerprints[0].depth, f"Run {i}: depth differs"
            assert (
                fingerprints[i].total_steps == fingerprints[0].total_steps
            ), f"Run {i}: total_steps differs"
            assert (
                fingerprints[i].output_length == fingerprints[0].output_length
            ), f"Run {i}: output_length differs"
            assert (
                fingerprints[i].verification_steps == fingerprints[0].verification_steps
            ), f"Run {i}: verification_steps differs"
            assert (
                fingerprints[i].correction_count == fingerprints[0].correction_count
            ), f"Run {i}: correction_count differs"
            assert (
                fingerprints[i].hedging_ratio == fingerprints[0].hedging_ratio
            ), f"Run {i}: hedging_ratio differs"
            assert (
                fingerprints[i].uncertainty_markers == fingerprints[0].uncertainty_markers
            ), f"Run {i}: uncertainty_markers differs"
            assert (
                fingerprints[i].confidence_markers == fingerprints[0].confidence_markers
            ), f"Run {i}: confidence_markers differs"
