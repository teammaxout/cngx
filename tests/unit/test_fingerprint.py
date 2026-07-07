"""Unit tests for fingerprint extraction."""

from datetime import datetime

import pytest

from cogscope.core.models import BehavioralFingerprint, ModelConfig, ReasoningTrace, TokenUsage, ToolCall
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.fingerprint.metrics import MetricsCalculator


@pytest.fixture
def mock_trace():
    """Create a sample trace for testing."""
    return ReasoningTrace(
        id="trace_test_123",
        timestamp=datetime.utcnow(),
        task_id="test_task",
        model="mock-model",
        model_config_params=ModelConfig(temperature=0.7),
        adapter_type="mock",
        system_message="You are a helpful assistant.",
        prompt="What is 2 + 2?",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2 + 2?"},
        ],
        tool_calls=[
            ToolCall(id="call_1", name="calculator", arguments={"expr": "2+2"}, result="4"),
        ],
        reasoning_tokens=["Let me think...", "2 + 2 equals 4", "The answer is 4"],
        reasoning_content="Let me think...\n2 + 2 equals 4\nThe answer is 4",
        output="The answer is 4.",
        finish_reason="stop",
        latency_ms=150.0,
        token_usage=TokenUsage(prompt_tokens=20, completion_tokens=30, total_tokens=50),
    )


@pytest.fixture
def mock_fingerprint():
    """Create a sample fingerprint for testing."""
    return BehavioralFingerprint(
        trace_id="trace_test_123",
        task_id="test_task",
        timestamp=datetime.utcnow(),
        model="mock-model",
        depth=3,
        branching_factor=0.5,
        total_steps=3,
        max_step_length=50,
        tool_call_count=1,
        tool_call_sequence=["calculator"],
        tool_diversity=1.0,
        tool_success_rate=1.0,
        output_length=15,
        reasoning_length=50,
        compression_ratio=0.3,
        avg_sentence_length=5.0,
        correction_count=0,
        backtrack_count=0,
        revision_count=0,
        uncertainty_markers=0,
        confidence_markers=1,
        hedging_ratio=0.0,
        verification_steps=1,
        example_count=0,
        structured_output=False,
        tokens_per_step=10.0,
        reasoning_overhead=0.5,
    )


class TestMetricsCalculator:
    """Tests for MetricsCalculator."""

    def test_calculate_depth_from_reasoning_tokens(self, mock_trace):
        """Test depth calculation from reasoning tokens."""
        calc = MetricsCalculator()
        depth = calc.calculate_depth(mock_trace)
        assert depth == 3  # mock_trace has 3 reasoning tokens

    def test_calculate_depth_from_output(self):
        """Test depth calculation from output when no reasoning tokens."""
        calc = MetricsCalculator()
        trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="Step 1: First.\nStep 2: Second.\nStep 3: Third.",
            reasoning_tokens=[],
        )
        depth = calc.calculate_depth(trace)
        assert depth == 3

    def test_count_corrections(self):
        """Test self-correction detection."""
        calc = MetricsCalculator()
        trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="Wait, actually I was wrong. Let me reconsider.",
            reasoning_content="Wait, actually I was wrong. Let me reconsider.",
        )
        count = calc.count_corrections(trace)
        assert count >= 2  # "wait", "actually", "let me reconsider"

    def test_count_uncertainty_markers(self):
        """Test uncertainty marker detection."""
        calc = MetricsCalculator()
        trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="I think this might be correct, possibly.",
        )
        count = calc.count_uncertainty_markers(trace)
        assert count >= 2  # "might", "possibly", "think"

    def test_count_confidence_markers(self):
        """Test confidence marker detection."""
        calc = MetricsCalculator()
        trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="This is definitely correct. Certainly the answer is 4.",
        )
        count = calc.count_confidence_markers(trace)
        assert count >= 2  # "definitely", "certainly"

    def test_calculate_hedging_ratio(self):
        """Test hedging ratio calculation."""
        calc = MetricsCalculator()

        # High uncertainty
        uncertain_trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="Maybe this might possibly be the answer.",
        )
        ratio1 = calc.calculate_hedging_ratio(uncertain_trace)
        assert ratio1 > 0.5

        # High confidence
        confident_trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="This is definitely, certainly, absolutely correct.",
        )
        ratio2 = calc.calculate_hedging_ratio(confident_trace)
        assert ratio2 < 0.5

    def test_detect_structured_output(self):
        """Test structured output detection."""
        calc = MetricsCalculator()

        # JSON output
        json_trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output='{"answer": 4}',
        )
        assert calc.detect_structured_output(json_trace) is True

        # Code block output
        code_trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="```python\nprint('hello')\n```",
        )
        assert calc.detect_structured_output(code_trace) is True

        # Plain text
        plain_trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="The answer is 4.",
        )
        assert calc.detect_structured_output(plain_trace) is False

    def test_count_verification_steps(self):
        """Test verification step detection."""
        calc = MetricsCalculator()
        trace = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="Let me verify this. I'll double-check the calculation.",
            reasoning_content="Let me verify this. I'll double-check the calculation.",
        )
        count = calc.count_verification_steps(trace)
        assert count >= 2

    def test_calculate_tool_diversity(self):
        """Test tool diversity calculation."""
        calc = MetricsCalculator()

        # All unique tools
        trace1 = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="test",
            tool_calls=[
                ToolCall(id="1", name="tool_a", arguments={}),
                ToolCall(id="2", name="tool_b", arguments={}),
                ToolCall(id="3", name="tool_c", arguments={}),
            ],
        )
        assert calc.calculate_tool_diversity(trace1) == 1.0

        # Repeated tools
        trace2 = ReasoningTrace(
            id="test",
            task_id="test",
            model="test",
            prompt="test",
            output="test",
            tool_calls=[
                ToolCall(id="1", name="tool_a", arguments={}),
                ToolCall(id="2", name="tool_a", arguments={}),
                ToolCall(id="3", name="tool_b", arguments={}),
            ],
        )
        diversity = calc.calculate_tool_diversity(trace2)
        assert diversity == pytest.approx(2 / 3, rel=0.01)


class TestFingerprintExtractor:
    """Tests for FingerprintExtractor."""

    def test_extract_basic(self, mock_trace):
        """Test basic fingerprint extraction."""
        extractor = FingerprintExtractor()
        fp = extractor.extract(mock_trace)

        assert fp.trace_id == mock_trace.id
        assert fp.task_id == mock_trace.task_id
        assert fp.depth > 0
        assert fp.tool_call_count == 1
        assert fp.signature_hash is not None

    def test_extract_preserves_model(self, mock_trace):
        """Test that model info is preserved."""
        extractor = FingerprintExtractor()
        fp = extractor.extract(mock_trace)
        assert fp.model == mock_trace.model

    def test_extract_signature_hash_deterministic(self, mock_trace):
        """Test that signature hash is deterministic."""
        extractor = FingerprintExtractor()
        fp1 = extractor.extract(mock_trace)
        fp2 = extractor.extract(mock_trace)
        assert fp1.signature_hash == fp2.signature_hash

    def test_compare_fingerprints(self, mock_trace):
        """Test fingerprint comparison."""
        extractor = FingerprintExtractor()
        fp1 = extractor.extract(mock_trace)
        fp2 = extractor.extract(mock_trace)

        # Same trace should have high similarity
        similarity = extractor.compare(fp1, fp2)
        assert similarity > 0.9

    def test_to_vector(self, mock_fingerprint):
        """Test vector conversion."""
        vector = mock_fingerprint.to_vector()
        assert len(vector) > 0
        assert all(isinstance(v, float) for v in vector)
