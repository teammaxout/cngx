"""
Shared fixtures for the brutal test suite.
Provides realistic traces, fingerprints, contracts, databases, and tracers.
"""

import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from cogscope.capture.tracer import CogscopeTracer
from cogscope.contracts.schema import BehaviorContract
from cogscope.contracts.validator import ContractValidator
from cogscope.core.models import (
    BehavioralFingerprint,
    ReasoningTrace,
    TokenUsage,
    ToolCall,
)
from cogscope.diff.engine import DiffEngine
from cogscope.drift.detector import DriftDetector
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.storage.database import Database
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
    STRUCTURED_CODE,
    TERSE_RESPONSE,
    VERBOSE_RESPONSE,
)

# ============================================================================
# Database & Storage
# ============================================================================


@pytest.fixture
def fresh_db(tmp_path):
    """Provide a fresh DuckDB database in a temp directory."""
    db_path = tmp_path / "test_cogscope.db"
    db = Database(db_path)
    yield db
    db.close()


@pytest.fixture
def populated_db(fresh_db):
    """Database pre-populated with traces and fingerprints."""
    extractor = FingerprintExtractor()
    traces = []
    for i, (output, task_id) in enumerate(
        [
            (GOOD_MATH_REASONING, "math_solve"),
            (SHALLOW_MATH, "math_solve"),
            (GOOD_CODE_REVIEW, "code_review"),
            (SHALLOW_CODE_REVIEW, "code_review"),
            (GOOD_RESEARCH, "research"),
            (HEDGING_RESPONSE, "research"),
        ]
    ):
        trace = ReasoningTrace(
            id=f"trace_{i:03d}",
            timestamp=datetime.utcnow(),
            task_id=task_id,
            model="test-model",
            adapter_type="mock",
            prompt=f"Test prompt {i}",
            output=output,
            latency_ms=100.0 + i * 50,
            token_usage=TokenUsage(
                prompt_tokens=50,
                completion_tokens=len(output.split()),
                total_tokens=50 + len(output.split()),
            ),
        )
        fresh_db.save_trace(trace)
        fp = extractor.extract(trace)
        fresh_db.save_fingerprint(fp)
        traces.append(trace)
    yield fresh_db, traces


# ============================================================================
# Trace Builders
# ============================================================================


def make_trace(
    output: str,
    task_id: str = "test_task",
    model: str = "test-model",
    reasoning_content: str = None,
    reasoning_tokens: list = None,
    tool_calls: list = None,
    trace_id: str = None,
    latency_ms: float = 150.0,
) -> ReasoningTrace:
    """Build a ReasoningTrace with sensible defaults."""
    return ReasoningTrace(
        id=trace_id or str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        task_id=task_id,
        model=model,
        adapter_type="mock",
        prompt="Test prompt",
        output=output,
        reasoning_content=reasoning_content,
        reasoning_tokens=reasoning_tokens or [],
        tool_calls=tool_calls or [],
        latency_ms=latency_ms,
        token_usage=TokenUsage(
            prompt_tokens=50,
            completion_tokens=max(1, len(output.split())),
            total_tokens=50 + max(1, len(output.split())),
        ),
    )


@pytest.fixture
def trace_good_math():
    return make_trace(GOOD_MATH_REASONING, task_id="math")


@pytest.fixture
def trace_shallow_math():
    return make_trace(SHALLOW_MATH, task_id="math")


@pytest.fixture
def trace_good_code():
    return make_trace(GOOD_CODE_REVIEW, task_id="code_review")


@pytest.fixture
def trace_shallow_code():
    return make_trace(SHALLOW_CODE_REVIEW, task_id="code_review")


@pytest.fixture
def trace_good_research():
    return make_trace(GOOD_RESEARCH, task_id="research")


@pytest.fixture
def trace_hedging():
    return make_trace(HEDGING_RESPONSE, task_id="research")


@pytest.fixture
def trace_overconfident():
    return make_trace(OVERCONFIDENT_WRONG, task_id="math")


@pytest.fixture
def trace_self_correcting():
    return make_trace(SELF_CORRECTING, task_id="math")


@pytest.fixture
def trace_verbose():
    return make_trace(VERBOSE_RESPONSE, task_id="math")


@pytest.fixture
def trace_terse():
    return make_trace(TERSE_RESPONSE, task_id="math")


@pytest.fixture
def trace_structured():
    return make_trace(STRUCTURED_CODE, task_id="code")


@pytest.fixture
def trace_empty():
    return make_trace(EMPTY_RESPONSE, task_id="test")


# ============================================================================
# Components
# ============================================================================


@pytest.fixture
def extractor():
    return FingerprintExtractor()


@pytest.fixture
def validator():
    return ContractValidator()


@pytest.fixture
def diff_engine():
    return DiffEngine()


@pytest.fixture
def mock_tracer(fresh_db):
    """CogscopeTracer with mock adapter and fresh database."""
    return CogscopeTracer(adapter="mock", model="mock-model", db=fresh_db)


# ============================================================================
# Contract Builders
# ============================================================================


def load_contract_from_string(yaml_str: str) -> BehaviorContract:
    """Parse a YAML string into a BehaviorContract."""
    data = yaml.safe_load(yaml_str)
    return BehaviorContract(**data)
