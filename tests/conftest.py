"""Pytest configuration for Cogscope tests."""

import tempfile
from pathlib import Path

import pytest

from cogscope.core.config import CogscopeConfig, reset_config
from cogscope.storage.database import Database, reset_database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / ".cogscope" / "test.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = Database(db_path)
        yield db
        db.close()


@pytest.fixture
def temp_config(temp_db):
    """Create a temporary config for testing."""
    reset_config()
    with tempfile.TemporaryDirectory() as tmpdir:
        config = CogscopeConfig(project_root=Path(tmpdir))
        yield config
    reset_config()


@pytest.fixture
def mock_trace():
    """Create a sample trace for testing."""
    from datetime import datetime

    from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall

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
    from datetime import datetime

    from cogscope.core.models import BehavioralFingerprint

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
