"""Unit tests for fingerprint metrics calculator.

Tests all metric extraction functions including the newly
implemented count_revisions().
"""

import pytest

from cogscope.core.models import ReasoningTrace
from cogscope.fingerprint.metrics import MetricsCalculator


@pytest.fixture
def calc():
    return MetricsCalculator()


class TestCountRevisions:
    """Tests for the revision detection metric."""

    def test_no_revisions(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="The answer is 42.",
        )
        assert calc.count_revisions(trace) == 0

    def test_upon_reflection(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Upon reflection, I think the answer is 42.",
        )
        assert calc.count_revisions(trace) >= 1

    def test_let_me_recalculate(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Let me recalculate that. The result is 7.",
        )
        assert calc.count_revisions(trace) >= 1

    def test_i_made_an_error(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Wait, I made an error earlier. The correct answer is 5.",
        )
        assert calc.count_revisions(trace) >= 1

    def test_multiple_revisions(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output=(
                "The answer is 10. Wait, that's incorrect, let me reconsider. "
                "Upon reflection, the correct answer is actually 12. "
                "I need to revise my earlier calculation."
            ),
        )
        assert calc.count_revisions(trace) >= 3

    def test_reasoning_content_checked(self, calc):
        """Revisions in reasoning_content should also be counted."""
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="42.",
            reasoning_content="I initially said 40, but after further analysis, the correct answer is 42.",
        )
        assert calc.count_revisions(trace) >= 1

    def test_changing_my_answer(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Changing my answer to 7.",
        )
        assert calc.count_revisions(trace) >= 1

    def test_after_further_thought(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="After further thought, 99 is correct.",
        )
        assert calc.count_revisions(trace) >= 1


class TestDepthCalculation:
    def test_depth_from_tokens(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="answer",
            reasoning_tokens=["step 1", "step 2", "step 3"],
        )
        assert calc.calculate_depth(trace) == 3

    def test_depth_from_step_indicators(self, calc):
        """Depth uses step indicators (Step 1, 1., etc.)"""
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Step 1: Analyze.\nStep 2: Calculate.\nStep 3: Verify.",
            reasoning_tokens=[],
        )
        assert calc.calculate_depth(trace) == 3

    def test_depth_from_paragraphs(self, calc):
        """Depth falls back to paragraph count (double newlines)."""
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
            reasoning_tokens=[],
        )
        assert calc.calculate_depth(trace) == 3

    def test_depth_empty_returns_one(self, calc):
        """Empty output returns max(1, ...) = 1."""
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="",
            reasoning_tokens=[],
        )
        # Implementation returns max(1, paragraphs) so empty still returns 1
        assert calc.calculate_depth(trace) >= 1


class TestHedgingRatio:
    def test_high_uncertainty(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="Maybe this might possibly perhaps be correct.",
        )
        ratio = calc.calculate_hedging_ratio(trace)
        assert ratio > 0.5

    def test_high_confidence(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="This is definitely certainly absolutely correct.",
        )
        ratio = calc.calculate_hedging_ratio(trace)
        assert ratio < 0.5

    def test_no_markers(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="The answer to the question.",
        )
        ratio = calc.calculate_hedging_ratio(trace)
        assert ratio == 0.5  # Neutral when no markers found


class TestToolCallMetrics:
    def test_tool_diversity_all_unique(self, calc):
        from cogscope.core.models import ToolCall

        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="result",
            tool_calls=[
                ToolCall(id="1", name="search", arguments={}, result="r1"),
                ToolCall(id="2", name="calculate", arguments={}, result="r2"),
                ToolCall(id="3", name="analyze", arguments={}, result="r3"),
            ],
        )
        diversity = calc.calculate_tool_diversity(trace)
        assert diversity == 1.0

    def test_tool_diversity_all_same(self, calc):
        from cogscope.core.models import ToolCall

        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="result",
            tool_calls=[
                ToolCall(id="1", name="search", arguments={}, result="r1"),
                ToolCall(id="2", name="search", arguments={}, result="r2"),
                ToolCall(id="3", name="search", arguments={}, result="r3"),
            ],
        )
        diversity = calc.calculate_tool_diversity(trace)
        assert abs(diversity - (1 / 3)) < 0.01

    def test_tool_diversity_no_tools(self, calc):
        trace = ReasoningTrace(
            id="t",
            task_id="t",
            model="m",
            prompt="p",
            output="result",
            tool_calls=[],
        )
        diversity = calc.calculate_tool_diversity(trace)
        assert diversity == 0.0
