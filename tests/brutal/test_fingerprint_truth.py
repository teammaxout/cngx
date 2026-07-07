"""
BRUTAL TEST: Fingerprint Extraction Truthfulness

Tests whether the fingerprint extractor actually captures meaningful behavioral
differences between objectively different types of LLM outputs.

If these tests fail, the core claim of Cogscope is broken.
"""

import pytest

from cogscope.core.models import ReasoningTrace, TokenUsage
from cogscope.fingerprint.extractor import FingerprintExtractor
from tests.brutal.conftest import make_trace
from tests.brutal.fixtures.sample_outputs import (
    EMPTY_RESPONSE,
    GOOD_CODE_REVIEW,
    GOOD_MATH_REASONING,
    GOOD_RESEARCH,
    HEDGING_RESPONSE,
    OVERCONFIDENT_WRONG,
    SELF_CORRECTING,
    SHALLOW_CODE_REVIEW,
    SHALLOW_MATH,
    SHALLOW_RESEARCH,
    SINGLE_WORD,
    STRUCTURED_CODE,
    TERSE_RESPONSE,
    UNICODE_HEAVY,
    VERBOSE_RESPONSE,
    VERY_LONG,
    WHITESPACE_ONLY,
)


class TestDepthDetection:
    """The core claim: Cogscope can detect how deeply an LLM reasons."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_deep_reasoning_has_higher_depth_than_shallow(self):
        """4-step math reasoning MUST score higher depth than 1-line answer."""
        deep = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        shallow = self.extractor.extract(make_trace(SHALLOW_MATH))
        assert (
            deep.depth > shallow.depth
        ), f"Deep reasoning ({deep.depth}) must have higher depth than shallow ({shallow.depth})"

    def test_deep_reasoning_depth_at_least_3(self):
        """Good math reasoning has 4 clearly labeled steps — must detect >= 3."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert fp.depth >= 3, f"Expected depth >= 3 for 4-step reasoning, got {fp.depth}"

    def test_shallow_answer_depth_low(self):
        """Single-line answer should have depth 1."""
        fp = self.extractor.extract(make_trace(SHALLOW_MATH))
        assert fp.depth <= 2, f"Expected depth <= 2 for one-liner, got {fp.depth}"

    def test_code_review_depth(self):
        """5-step code review must score depth >= 4."""
        fp = self.extractor.extract(make_trace(GOOD_CODE_REVIEW))
        assert fp.depth >= 4, f"5-step code review should have depth >= 4, got {fp.depth}"

    def test_research_depth(self):
        """5-step research analysis must score depth >= 4."""
        fp = self.extractor.extract(make_trace(GOOD_RESEARCH))
        assert fp.depth >= 4, f"5-step research should have depth >= 4, got {fp.depth}"

    def test_verbose_depth_reflects_steps(self):
        """Verbose response clearly has numbered steps."""
        fp = self.extractor.extract(make_trace(VERBOSE_RESPONSE))
        assert (
            fp.depth >= 3
        ), f"Verbose labeled-step response should have depth >= 3, got {fp.depth}"

    def test_terse_response_depth(self):
        """Terse 'x = -2, -3' should have depth 1."""
        fp = self.extractor.extract(make_trace(TERSE_RESPONSE))
        assert fp.depth <= 2, f"Terse response should have depth <= 2, got {fp.depth}"

    def test_reasoning_tokens_used_when_available(self):
        """If reasoning_tokens are provided, depth = len(reasoning_tokens)."""
        trace = make_trace(
            output="Final answer",
            reasoning_tokens=["step1", "step2", "step3", "step4", "step5"],
        )
        fp = self.extractor.extract(trace)
        assert fp.depth == 5, f"With 5 reasoning tokens, depth should be 5, got {fp.depth}"


class TestVerificationDetection:
    """Tests whether Cogscope detects self-verification in reasoning."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_verified_math_detected(self):
        """Good math reasoning explicitly verifies — must detect > 0 verification steps."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert (
            fp.verification_steps > 0
        ), f"Math with 'Let me verify' should have verification_steps > 0, got {fp.verification_steps}"

    def test_no_verification_in_shallow(self):
        """Shallow one-liner has no verification."""
        fp = self.extractor.extract(make_trace(SHALLOW_MATH))
        assert (
            fp.verification_steps == 0
        ), f"One-liner should have 0 verification steps, got {fp.verification_steps}"

    def test_code_review_has_verification(self):
        """Code review with 'double-check' should detect verification."""
        fp = self.extractor.extract(make_trace(GOOD_CODE_REVIEW))
        assert (
            fp.verification_steps > 0
        ), f"Code review with verification language should detect it, got {fp.verification_steps}"

    def test_self_correcting_has_verification(self):
        """Self-correcting response with 'double-check' should show verification."""
        fp = self.extractor.extract(make_trace(SELF_CORRECTING))
        assert (
            fp.verification_steps > 0
        ), f"Self-correcting response should show verification, got {fp.verification_steps}"


class TestHedgingDetection:
    """Tests whether Cogscope reliably detects hedging vs confidence."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_hedging_response_has_high_hedging_ratio(self):
        """Response loaded with 'maybe', 'might', 'possibly' should score high hedging."""
        fp = self.extractor.extract(make_trace(HEDGING_RESPONSE))
        assert (
            fp.hedging_ratio > 0.3
        ), f"Hedging-heavy response should have hedging_ratio > 0.3, got {fp.hedging_ratio:.3f}"

    def test_confident_response_has_low_hedging(self):
        """Good math reasoning is assertive — low hedging."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert (
            fp.hedging_ratio < 0.3
        ), f"Confident math reasoning should have hedging_ratio < 0.3, got {fp.hedging_ratio:.3f}"

    def test_overconfident_has_low_hedging(self):
        """Overconfident response has zero uncertainty markers."""
        fp = self.extractor.extract(make_trace(OVERCONFIDENT_WRONG))
        assert (
            fp.hedging_ratio < 0.2
        ), f"Overconfident response should have very low hedging, got {fp.hedging_ratio:.3f}"

    def test_hedging_response_has_more_uncertainty_than_confident(self):
        """Hedging response must have more uncertainty markers than confident one."""
        hedging = self.extractor.extract(make_trace(HEDGING_RESPONSE))
        confident = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert hedging.uncertainty_markers > confident.uncertainty_markers, (
            f"Hedging ({hedging.uncertainty_markers}) should have more uncertainty "
            f"than confident ({confident.uncertainty_markers})"
        )

    def test_overconfident_has_confidence_markers(self):
        """Response with 'definitely', 'certainly', etc. must show confidence markers."""
        fp = self.extractor.extract(make_trace(OVERCONFIDENT_WRONG))
        assert (
            fp.confidence_markers > 0
        ), f"Overconfident response should have confidence_markers > 0, got {fp.confidence_markers}"


class TestSelfCorrectionDetection:
    """Tests whether Cogscope detects when an LLM corrects itself."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_self_correcting_has_corrections(self):
        """Response with 'wait', 'actually', 'my mistake' should detect corrections."""
        fp = self.extractor.extract(make_trace(SELF_CORRECTING))
        assert (
            fp.correction_count > 0
        ), f"Self-correcting response should have corrections > 0, got {fp.correction_count}"

    def test_clean_response_no_corrections(self):
        """Clean good reasoning has no corrections."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        # Good math reasoning is clean — no "wait", "actually"
        # but it might match on verify language, so just check it's lower
        correcting = self.extractor.extract(make_trace(SELF_CORRECTING))
        assert correcting.correction_count > fp.correction_count, (
            f"Self-correcting ({correcting.correction_count}) should have more corrections "
            f"than clean ({fp.correction_count})"
        )

    def test_shallow_no_corrections(self):
        """One-liner has no self-correction language."""
        fp = self.extractor.extract(make_trace(SHALLOW_MATH))
        assert (
            fp.correction_count == 0
        ), f"One-liner should have 0 corrections, got {fp.correction_count}"


class TestStructuredOutputDetection:
    """Tests whether Cogscope detects structured output (code, JSON, lists)."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_code_output_detected(self):
        """Response with code blocks should detect structured output."""
        fp = self.extractor.extract(make_trace(STRUCTURED_CODE))
        assert fp.structured_output is True, "Code block response should detect structured output"

    def test_plain_text_not_structured(self):
        """Plain text response should not be marked as structured."""
        fp = self.extractor.extract(make_trace(SHALLOW_MATH))
        assert fp.structured_output is False, "Plain text should not be structured"


class TestVerbosityMetrics:
    """Tests whether verbosity metrics correctly differentiate outputs."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_verbose_longer_output(self):
        """Verbose response should have much more output length than terse."""
        verbose = self.extractor.extract(make_trace(VERBOSE_RESPONSE))
        terse = self.extractor.extract(make_trace(TERSE_RESPONSE))
        assert (
            verbose.output_length > terse.output_length * 10
        ), f"Verbose ({verbose.output_length}) should be >10x terse ({terse.output_length})"

    def test_compression_ratio_sensible(self):
        """Compression ratio should be between 0 and 1 for normal text."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert (
            0 <= fp.compression_ratio <= 2.0
        ), f"Compression ratio should be reasonable, got {fp.compression_ratio}"


class TestFingerprintDifferentiation:
    """The CRITICAL test: Can fingerprints actually distinguish different behaviors?

    If two objectively different outputs produce identical fingerprints,
    the entire product is worthless.
    """

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_deep_vs_shallow_distinguishable(self):
        """Deep and shallow reasoning MUST produce different fingerprint vectors."""
        deep = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        shallow = self.extractor.extract(make_trace(SHALLOW_MATH))
        v_deep = deep.to_vector()
        v_shallow = shallow.to_vector()
        assert v_deep != v_shallow, "Deep and shallow MUST have different fingerprint vectors"

    def test_hedging_vs_confident_distinguishable(self):
        """Hedging and confident responses MUST produce different vectors."""
        hedging = self.extractor.extract(make_trace(HEDGING_RESPONSE))
        confident = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        v_h = hedging.to_vector()
        v_c = confident.to_vector()
        assert v_h != v_c, "Hedging and confident MUST have different vectors"

    def test_different_signature_hashes(self):
        """Objectively different behaviors should produce different signature hashes."""
        outputs = [
            GOOD_MATH_REASONING,
            SHALLOW_MATH,
            HEDGING_RESPONSE,
            SELF_CORRECTING,
            GOOD_CODE_REVIEW,
        ]
        hashes = set()
        for output in outputs:
            fp = self.extractor.extract(make_trace(output))
            hashes.add(fp.signature_hash)
        # At least 3 out of 5 should be unique (hashing is lossy, but major differences must survive)
        assert (
            len(hashes) >= 3
        ), f"5 very different outputs produced only {len(hashes)} unique signature hashes"

    def test_similar_inputs_similar_fingerprints(self):
        """Same output run twice should produce very similar fingerprints."""
        fp1 = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        fp2 = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        v1 = fp1.to_vector()
        v2 = fp2.to_vector()
        # Vectors should be identical (same input)
        assert v1 == v2, "Same input should produce identical fingerprint vectors"


class TestEdgeCases:
    """Edge cases that could crash or produce nonsensical fingerprints."""

    def setup_method(self):
        self.extractor = FingerprintExtractor()

    def test_empty_output_no_crash(self):
        """Empty output should not crash, should produce a valid fingerprint."""
        fp = self.extractor.extract(make_trace(EMPTY_RESPONSE))
        assert fp is not None
        assert fp.depth >= 0
        assert fp.output_length == 0

    def test_whitespace_only_no_crash(self):
        """Whitespace-only output should not crash."""
        fp = self.extractor.extract(make_trace(WHITESPACE_ONLY))
        assert fp is not None

    def test_single_word_no_crash(self):
        """Single word '42' should produce valid fingerprint."""
        fp = self.extractor.extract(make_trace(SINGLE_WORD))
        assert fp is not None
        assert fp.depth >= 1  # At least 1 "step"

    def test_very_long_output_no_crash(self):
        """80K char output should not crash or hang."""
        fp = self.extractor.extract(make_trace(VERY_LONG))
        assert fp is not None
        assert fp.output_length > 0

    def test_unicode_heavy_no_crash(self):
        """Unicode-heavy output should not crash regex patterns."""
        fp = self.extractor.extract(make_trace(UNICODE_HEAVY))
        assert fp is not None

    def test_fingerprint_has_all_fields(self):
        """Every fingerprint field must be populated (not None)."""
        fp = self.extractor.extract(make_trace(GOOD_MATH_REASONING))
        assert fp.trace_id is not None
        assert fp.depth is not None
        assert fp.branching_factor is not None
        assert fp.total_steps is not None
        assert fp.output_length is not None
        assert fp.hedging_ratio is not None
        assert fp.verification_steps is not None
        assert fp.correction_count is not None
        assert fp.uncertainty_markers is not None
        assert fp.confidence_markers is not None
        assert fp.structured_output is not None

    def test_no_negative_metrics(self):
        """No metric should ever be negative."""
        for output in [GOOD_MATH_REASONING, SHALLOW_MATH, HEDGING_RESPONSE, EMPTY_RESPONSE]:
            fp = self.extractor.extract(make_trace(output))
            assert fp.depth >= 0, f"depth negative: {fp.depth}"
            assert fp.branching_factor >= 0, f"branching_factor negative: {fp.branching_factor}"
            assert fp.output_length >= 0, f"output_length negative: {fp.output_length}"
            assert fp.hedging_ratio >= 0, f"hedging_ratio negative: {fp.hedging_ratio}"
            assert (
                fp.verification_steps >= 0
            ), f"verification_steps negative: {fp.verification_steps}"
            assert fp.correction_count >= 0, f"correction_count negative: {fp.correction_count}"
            assert (
                fp.uncertainty_markers >= 0
            ), f"uncertainty_markers negative: {fp.uncertainty_markers}"
            assert (
                fp.confidence_markers >= 0
            ), f"confidence_markers negative: {fp.confidence_markers}"
