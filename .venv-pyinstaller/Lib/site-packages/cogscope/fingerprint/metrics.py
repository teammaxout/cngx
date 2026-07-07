"""Metrics calculation for behavioral fingerprinting."""

import re
from typing import Any

from cogscope.core.models import ReasoningTrace


class MetricsCalculator:
    """Calculate behavioral metrics from reasoning traces.

    This class extracts quantifiable behavioral signals from traces,
    forming the basis for fingerprint generation.
    """

    # Patterns for detecting self-correction
    CORRECTION_PATTERNS = [
        r"\bwait\b",
        r"\bactually\b",
        r"\blet me reconsider\b",
        r"\bon second thought\b",
        r"\bI was wrong\b",
        r"\bmy mistake\b",
        r"\bcorrection\b",
        r"\bscratch that\b",
        r"\bno[,\s]+that's not right\b",
    ]

    # Patterns for uncertainty
    UNCERTAINTY_PATTERNS = [
        r"\bmight\b",
        r"\bpossibly\b",
        r"\bperhaps\b",
        r"\bmaybe\b",
        r"\bunclear\b",
        r"\bnot sure\b",
        r"\buncertain\b",
        r"\bcould be\b",
        r"\bseems like\b",
        r"\bI think\b",
        r"\bprobably\b",
    ]

    # Patterns for confidence
    CONFIDENCE_PATTERNS = [
        r"\bdefinitely\b",
        r"\bcertainly\b",
        r"\bclearly\b",
        r"\bobviously\b",
        r"\bwithout doubt\b",
        r"\bI'm confident\b",
        r"\bI'm sure\b",
        r"\babsolutely\b",
        r"\bno question\b",
        # Academic/formal confidence markers
        r"\bdemonstrates that\b",
        r"\bestablishes that\b",
        r"\bconfirms that\b",
        r"\bshows that\b",
        r"\bproves that\b",
        r"\bmust be\b",
        r"\bnecessarily\b",
        r"\bthis means\b",
        r"\btherefore\b",
        r"\bthus\b",
        r"\bhence\b",
        r"\bconsequently\b",
        r"\bin fact\b",
        r"\bindeed\b",
        r"\bspecifically\b",
        r"\bprecisely\b",
        r"\bwe can conclude\b",
        r"\bit follows that\b",
        r"\bwe know that\b",
        r"\bthe answer is\b",
    ]

    # Patterns for verification
    VERIFICATION_PATTERNS = [
        r"\blet me verify\b",
        r"\blet me check\b",
        r"\blet's check\b",
        r"\blet's verify\b",
        r"\bwe can verify\b",
        r"\bwe can check\b",
        r"\bto verify\b",
        r"\bto check\b",
        r"\bdouble.check\b",
        r"\bcross.check\b",
        r"\bverif(?:y|ying|ied|ication)\b",
        r"\bchecking\b",
        r"\bconfirm(?:ing|ed|s)?\b",
        r"\bvalidat(?:e|ing|ed|ion)\b",
        r"\bmake sure\b",
        r"\bcheck(?:ing)?:\s",
        r"\bproof:\s",
        r"\bverification:\s",
        r"\bsanity check\b",
        r"\bindeed\b",
        r"\bcorrect\b",
        r"\btherefore.*=\s*\d",
        r"\bthus.*=\s*\d",
    ]

    # Patterns for backtracking
    BACKTRACK_PATTERNS = [
        r"\bgoing back\b",
        r"\blet me start over\b",
        r"\bretrying\b",
        r"\bback to\b",
        r"\brevisiting\b",
    ]

    def __init__(self):
        # Compile patterns for efficiency
        self._correction_re = [re.compile(p, re.IGNORECASE) for p in self.CORRECTION_PATTERNS]
        self._uncertainty_re = [re.compile(p, re.IGNORECASE) for p in self.UNCERTAINTY_PATTERNS]
        self._confidence_re = [re.compile(p, re.IGNORECASE) for p in self.CONFIDENCE_PATTERNS]
        self._verification_re = [re.compile(p, re.IGNORECASE) for p in self.VERIFICATION_PATTERNS]
        self._backtrack_re = [re.compile(p, re.IGNORECASE) for p in self.BACKTRACK_PATTERNS]

    def calculate_depth(self, trace: ReasoningTrace) -> int:
        """Calculate reasoning chain depth.

        Depth is the number of distinct reasoning steps, determined by:
        - Explicit reasoning tokens (if available)
        - Paragraph/section breaks
        - Step indicators ("1.", "Step 1:", etc.)
        """
        if trace.reasoning_tokens:
            return len(trace.reasoning_tokens)

        # Fall back to analyzing output structure
        content = trace.reasoning_content or trace.output

        # Count step indicators
        step_pattern = re.compile(
            r"^(?:\d+\.|Step \d+|First|Second|Third|Fourth|Fifth|Finally|Then|Next)",
            re.MULTILINE | re.IGNORECASE,
        )
        steps = step_pattern.findall(content)

        if steps:
            return len(steps)

        # Count paragraphs as a fallback
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        return max(1, len(paragraphs))

    def calculate_branching_factor(self, trace: ReasoningTrace) -> float:
        """Calculate average branching factor.

        Branching indicates how often the model considers alternatives
        or explores multiple paths.
        """
        content = trace.reasoning_content or trace.output

        # Patterns indicating alternatives being considered
        alternative_patterns = [
            r"\bor\b",
            r"\balternatively\b",
            r"\banother approach\b",
            r"\bon the other hand\b",
            r"\bcould also\b",
            r"\bwe could\b",
        ]

        total_branches = 0
        for pattern in alternative_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            total_branches += len(matches)

        depth = self.calculate_depth(trace)
        if depth == 0:
            return 0.0

        return total_branches / depth

    def count_corrections(self, trace: ReasoningTrace) -> int:
        """Count self-correction markers."""
        content = trace.reasoning_content or trace.output
        count = 0
        for pattern in self._correction_re:
            count += len(pattern.findall(content))
        return count

    def count_uncertainty_markers(self, trace: ReasoningTrace) -> int:
        """Count uncertainty markers."""
        content = trace.reasoning_content or trace.output
        count = 0
        for pattern in self._uncertainty_re:
            count += len(pattern.findall(content))
        return count

    def count_confidence_markers(self, trace: ReasoningTrace) -> int:
        """Count confidence markers."""
        content = trace.reasoning_content or trace.output
        count = 0
        for pattern in self._confidence_re:
            count += len(pattern.findall(content))
        return count

    def count_verification_steps(self, trace: ReasoningTrace) -> int:
        """Count verification steps."""
        content = trace.reasoning_content or trace.output
        count = 0
        for pattern in self._verification_re:
            count += len(pattern.findall(content))
        return count

    def count_backtrack(self, trace: ReasoningTrace) -> int:
        """Count backtracking instances."""
        content = trace.reasoning_content or trace.output
        count = 0
        for pattern in self._backtrack_re:
            count += len(pattern.findall(content))
        return count

    def calculate_hedging_ratio(self, trace: ReasoningTrace) -> float:
        """Calculate the hedging ratio (uncertainty / (uncertainty + confidence)).

        Higher values indicate more hedging/uncertainty in reasoning.
        """
        uncertainty = self.count_uncertainty_markers(trace)
        confidence = self.count_confidence_markers(trace)

        total = uncertainty + confidence
        if total == 0:
            return 0.5  # Neutral

        return uncertainty / total

    def calculate_compression_ratio(self, trace: ReasoningTrace) -> float:
        """Calculate output/reasoning compression ratio.

        Lower values indicate more internal reasoning for less output.
        """
        reasoning_length = len(trace.reasoning_content or "")
        output_length = len(trace.output)

        if reasoning_length == 0:
            return 1.0  # No reasoning captured

        return output_length / reasoning_length

    def calculate_avg_sentence_length(self, trace: ReasoningTrace) -> float:
        """Calculate average sentence length in the output."""
        content = trace.output

        # Simple sentence splitting
        sentences = re.split(r"[.!?]+", content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return 0.0

        total_words = sum(len(s.split()) for s in sentences)
        return total_words / len(sentences)

    def count_examples(self, trace: ReasoningTrace) -> int:
        """Count examples provided in the response."""
        content = trace.reasoning_content or trace.output

        example_patterns = [
            r"\bfor example\b",
            r"\bfor instance\b",
            r"\be\.g\.",
            r"\bsuch as\b",
            r"\bconsider\b",
            r"\bimagine\b",
        ]

        count = 0
        for pattern in example_patterns:
            count += len(re.findall(pattern, content, re.IGNORECASE))

        return count

    def detect_structured_output(self, trace: ReasoningTrace) -> bool:
        """Detect if output uses structured format (JSON, code, etc.)."""
        output = trace.output

        # Check for code blocks
        if "```" in output:
            return True

        # Check for JSON-like structures
        if output.strip().startswith("{") or output.strip().startswith("["):
            return True

        # Check for numbered/bulleted lists
        list_pattern = re.compile(r"^[\s]*[\-\*\d]+[.\)]\s", re.MULTILINE)
        if len(list_pattern.findall(output)) >= 3:
            return True

        return False

    def calculate_tool_diversity(self, trace: ReasoningTrace) -> float:
        """Calculate tool usage diversity.

        Returns ratio of unique tools to total tool calls.
        """
        if not trace.tool_calls:
            return 0.0

        unique_tools = len(set(tc.name for tc in trace.tool_calls))
        total_calls = len(trace.tool_calls)

        return unique_tools / total_calls

    def calculate_tokens_per_step(self, trace: ReasoningTrace) -> float:
        """Calculate average tokens per reasoning step."""
        depth = self.calculate_depth(trace)
        if depth == 0:
            return 0.0

        total_tokens = trace.token_usage.completion_tokens
        return total_tokens / depth

    def calculate_reasoning_overhead(self, trace: ReasoningTrace) -> float:
        """Calculate reasoning token overhead.

        Ratio of reasoning tokens to output tokens.
        """
        reasoning_tokens = trace.token_usage.reasoning_tokens
        completion_tokens = trace.token_usage.completion_tokens

        if completion_tokens == 0 or reasoning_tokens == 0:
            return 0.0

        # If reasoning tokens are part of completion, calculate the overhead
        if reasoning_tokens < completion_tokens:
            return reasoning_tokens / (completion_tokens - reasoning_tokens)
        else:
            return reasoning_tokens / completion_tokens

    def count_revisions(self, trace: ReasoningTrace) -> int:
        """Count revised conclusions in reasoning.

        Detects patterns where the model changes its final answer
        or revises a previously stated conclusion.
        """
        content = trace.reasoning_content or trace.output

        revision_patterns = [
            re.compile(r"\bupon reflection\b", re.IGNORECASE),
            re.compile(r"\bI need to revise\b", re.IGNORECASE),
            re.compile(r"\blet me recalculate\b", re.IGNORECASE),
            re.compile(r"\bthat's incorrect\b", re.IGNORECASE),
            re.compile(r"\bI made an error\b", re.IGNORECASE),
            re.compile(r"\bthe correct answer\b", re.IGNORECASE),
            re.compile(r"\bupdating my answer\b", re.IGNORECASE),
            re.compile(r"\bafter further (thought|analysis|review)\b", re.IGNORECASE),
            re.compile(r"\bI initially (said|thought|wrote)\b", re.IGNORECASE),
            re.compile(r"\bchanging my (answer|conclusion|response)\b", re.IGNORECASE),
        ]

        count = 0
        for pattern in revision_patterns:
            count += len(pattern.findall(content))
        return count
