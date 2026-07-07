"""Core data models for Cogscope.

These Pydantic models define the schema for reasoning traces,
behavioral fingerprints, and behavior diffs.
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


class TokenUsage(BaseModel):
    """Token usage statistics for an LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0  # For models that expose CoT tokens


class ToolCall(BaseModel):
    """A single tool call made during reasoning."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0


class ModelConfig(BaseModel):
    """Configuration for the LLM call."""

    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: Optional[int] = None
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    stop: Optional[list[str]] = None
    seed: Optional[int] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ReasoningTrace(BaseModel):
    """A complete reasoning trace from an LLM call.

    This captures everything about how the model reasoned:
    - The input (prompt, system message, config)
    - The process (tool calls, reasoning tokens)
    - The output (final response)
    - Metadata (timing, tokens, model info)
    """

    id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    task_id: str
    task_description: Optional[str] = None

    # Model info
    model: str
    model_config_params: ModelConfig = Field(default_factory=ModelConfig)
    adapter_type: str = "unknown"

    # Input
    system_message: Optional[str] = None
    prompt: str
    messages: list[dict[str, Any]] = Field(default_factory=list)

    # Process
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning_tokens: list[str] = Field(default_factory=list)
    reasoning_content: Optional[str] = None  # Full CoT if available

    # Output
    output: str
    finish_reason: Optional[str] = None

    # Metadata
    latency_ms: float = 0.0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def content_hash(self) -> str:
        """Hash of the trace content for deduplication."""
        content = f"{self.task_id}:{self.prompt}:{self.output}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class SignificanceLevel(str, Enum):
    """Significance level for behavioral changes."""

    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CRITICAL = "critical"


class ChangeType(str, Enum):
    """Type of behavioral change."""

    ADDED = "added"
    REMOVED = "removed"
    INCREASED = "increased"
    DECREASED = "decreased"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class BehavioralFingerprint(BaseModel):
    """Behavioral fingerprint extracted from a reasoning trace.

    This captures the "shape" of reasoning, independent of specific content:
    - Structural patterns (depth, branching)
    - Tool usage patterns
    - Verbosity and compression
    - Self-correction and uncertainty markers
    """

    trace_id: str
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Structural metrics
    depth: int = 0  # Reasoning chain depth
    branching_factor: float = 0.0  # Average branches per reasoning step
    total_steps: int = 0  # Total reasoning steps identified
    max_step_length: int = 0  # Longest single step

    # Tool usage
    tool_call_count: int = 0
    tool_call_sequence: list[str] = Field(default_factory=list)
    tool_diversity: float = 0.0  # Unique tools / total calls
    tool_success_rate: float = 1.0

    # Verbosity metrics
    output_length: int = 0  # Characters in output
    reasoning_length: int = 0  # Characters in reasoning
    compression_ratio: float = 0.0  # output / reasoning
    avg_sentence_length: float = 0.0

    # Self-correction markers
    correction_count: int = 0  # "wait", "actually", "let me reconsider"
    backtrack_count: int = 0  # Explicit backtracking
    revision_count: int = 0  # Revisions to previous statements

    # Uncertainty markers
    uncertainty_markers: int = 0  # "might", "possibly", "unclear"
    confidence_markers: int = 0  # "definitely", "certainly", "clearly"
    hedging_ratio: float = 0.0  # uncertainty / (uncertainty + confidence)

    # Quality signals
    verification_steps: int = 0  # Self-verification attempts
    example_count: int = 0  # Examples provided
    structured_output: bool = False  # Uses structured format

    # Token efficiency
    tokens_per_step: float = 0.0
    reasoning_overhead: float = 0.0  # reasoning_tokens / output_tokens

    # Metadata
    model: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def signature_hash(self) -> str:
        """Normalized fingerprint hash for quick comparison.

        This hash captures the behavioral signature, allowing quick
        identification of similar reasoning patterns.
        """
        # Key metrics that define the behavioral signature
        signature_data = {
            "depth": self.depth,
            "branching": round(self.branching_factor, 2),
            "steps": self.total_steps,
            "tool_count": self.tool_call_count,
            "tool_sequence": self.tool_call_sequence[:5],  # First 5 tools
            "corrections": self.correction_count > 0,
            "uncertainty": self.hedging_ratio > 0.3,
            "verification": self.verification_steps > 0,
        }
        content = json.dumps(signature_data, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_vector(self) -> list[float]:
        """Convert fingerprint to numerical vector for comparison."""
        return [
            float(self.depth),
            self.branching_factor,
            float(self.total_steps),
            float(self.tool_call_count),
            self.tool_diversity,
            float(self.output_length) / 1000,  # Normalize
            float(self.reasoning_length) / 1000,
            self.compression_ratio,
            float(self.correction_count),
            float(self.uncertainty_markers),
            float(self.confidence_markers),
            self.hedging_ratio,
            float(self.verification_steps),
            self.tokens_per_step / 100,
        ]


class BehaviorChange(BaseModel):
    """A single behavioral change between fingerprints."""

    metric: str
    baseline_value: Any
    current_value: Any
    change_type: ChangeType
    magnitude: float = 0.0  # Normalized magnitude of change
    significance: SignificanceLevel = SignificanceLevel.NONE
    description: str = ""


class BehaviorDiff(BaseModel):
    """Complete diff between two behavioral fingerprints.

    This is the core output that shows how behavior has changed.
    """

    baseline_id: str
    current_id: str
    baseline_task_id: str
    current_task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Changes
    changes: list[BehaviorChange] = Field(default_factory=list)

    # Summary metrics
    drift_score: float = 0.0  # 0-1, higher = more drift
    significance: SignificanceLevel = SignificanceLevel.NONE
    total_changes: int = 0
    breaking_changes: int = 0

    # Analysis
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def has_regression(self) -> bool:
        """Whether this diff indicates a potential regression."""
        return any(
            c.significance in [SignificanceLevel.MAJOR, SignificanceLevel.CRITICAL]
            for c in self.changes
        )


class Baseline(BaseModel):
    """A pinned baseline behavior for comparison."""

    id: str
    name: str
    description: Optional[str] = None
    task_id: str
    fingerprint_id: str
    trace_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class DriftReport(BaseModel):
    """Report of drift over a time window."""

    id: str
    task_id: str
    baseline_id: Optional[str] = None
    start_time: datetime
    end_time: datetime

    # Drift analysis
    drift_score: float = 0.0
    drift_trend: str = "stable"  # stable, increasing, decreasing
    significant_changes: list[BehaviorChange] = Field(default_factory=list)

    # Statistical analysis
    sample_count: int = 0
    variance: float = 0.0
    std_deviation: float = 0.0
    z_scores: dict[str, float] = Field(default_factory=dict)

    summary: str = ""


class EvalResult(BaseModel):
    """Result of a single evaluation."""

    id: str
    task_id: str
    trace_id: str
    fingerprint_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Evaluation
    passed: bool
    score: float = 0.0
    expected_behavior: dict[str, Any] = Field(default_factory=dict)
    actual_behavior: dict[str, Any] = Field(default_factory=dict)

    # Comparison to baseline
    baseline_id: Optional[str] = None
    drift_from_baseline: Optional[float] = None
    is_regression: bool = False

    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class EvalSuite(BaseModel):
    """A suite of evaluations to run."""

    id: str
    name: str
    description: Optional[str] = None
    task_ids: list[str] = Field(default_factory=list)
    baseline_ids: dict[str, str] = Field(default_factory=dict)  # task_id -> baseline_id
    thresholds: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
