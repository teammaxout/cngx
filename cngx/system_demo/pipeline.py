"""AI Decision Pipeline - A multi-stage pipeline that relies on AI reasoning.

This represents a REAL pattern in production AI systems:
1. User input arrives
2. LLM interprets/reasons about the input
3. Downstream code TRUSTS the LLM's reasoning
4. Decisions are made based on that trust

When reasoning quality silently degrades, the entire system becomes unsafe.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


class PipelineStage(str, Enum):
    """Stages in the AI decision pipeline."""

    INPUT = "input"
    INTERPRET = "interpret"  # LLM interprets the problem
    REASON = "reason"  # LLM reasons through solution
    VERIFY = "verify"  # LLM verifies its work
    DECIDE = "decide"  # Downstream logic makes decision
    OUTPUT = "output"


class StageResult(BaseModel):
    """Result from a single pipeline stage."""

    stage: PipelineStage
    success: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Content
    input_data: Any = None
    output_data: Any = None

    # Reasoning artifacts
    reasoning_content: Optional[str] = None
    verification_performed: bool = False
    confidence_score: float = 0.0

    # Downstream implications
    downstream_safe: bool = True
    downstream_assumptions: list[str] = Field(default_factory=list)

    # Debug
    raw_llm_output: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "success": self.success,
            "verification_performed": self.verification_performed,
            "confidence_score": self.confidence_score,
            "downstream_safe": self.downstream_safe,
            "assumptions": self.downstream_assumptions,
        }


class PipelineResult(BaseModel):
    """Complete result from the AI decision pipeline."""

    # Identity
    pipeline_id: str
    scenario: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Stage results
    stages: dict[str, StageResult] = Field(default_factory=dict)

    # Overall status
    completed: bool = False
    success: bool = False

    # Critical safety flag
    reasoning_assumptions_violated: bool = False
    violated_assumptions: list[str] = Field(default_factory=list)

    # Downstream safety
    downstream_would_execute: bool = True
    downstream_execution_safe: bool = True
    downstream_risk_level: str = "unknown"

    # LLM artifacts
    trace_id: Optional[str] = None
    fingerprint_id: Optional[str] = None
    model: str = ""

    # Final output
    final_answer: Optional[str] = None

    # cngx gate result (if run with cngx)
    cngx_blocked: bool = False
    cngx_violations: list[dict] = Field(default_factory=list)

    def add_stage(self, result: StageResult):
        """Add a stage result."""
        self.stages[result.stage.value] = result

    def get_stage(self, stage: PipelineStage) -> Optional[StageResult]:
        """Get result for a specific stage."""
        return self.stages.get(stage.value)

    def summarize(self) -> str:
        """Human-readable summary of pipeline execution."""
        lines = [
            f"Pipeline: {self.scenario}",
            f"Status: {'SUCCESS' if self.success else 'FAILED'}",
            f"Completed: {self.completed}",
            "",
            "Stages:",
        ]

        for stage_name, result in self.stages.items():
            status = "✓" if result.success else "✗"
            verify = "V" if result.verification_performed else "-"
            safe = "S" if result.downstream_safe else "!"
            lines.append(
                f"  [{status}|{verify}|{safe}] {stage_name}: conf={result.confidence_score:.1%}"
            )

        if self.reasoning_assumptions_violated:
            lines.extend(
                [
                    "",
                    "⚠️  REASONING ASSUMPTIONS VIOLATED:",
                ]
            )
            for v in self.violated_assumptions:
                lines.append(f"    • {v}")

        if self.cngx_blocked:
            lines.extend(
                [
                    "",
                    "🛑 cngx BLOCKED DEPLOYMENT",
                ]
            )

        return "\n".join(lines)


class PipelineConfig(BaseModel):
    """Configuration for the AI decision pipeline."""

    # Model settings
    model: str = "gemini-flash-latest"
    adapter: str = "gemini"

    # Pipeline behavior
    stop_on_failure: bool = False  # Whether to halt pipeline on stage failure

    # Downstream assumptions (what downstream code EXPECTS from the LLM)
    require_verification: bool = True
    require_step_by_step: bool = True
    require_confidence: bool = True
    min_confidence_threshold: float = 0.7
    min_reasoning_depth: int = 3

    # Timeout
    stage_timeout_ms: float = 30000.0


@dataclass
class DownstreamConsumer:
    """Represents downstream code that TRUSTS AI reasoning.

    This is the critical insight: downstream code makes assumptions
    about the quality of AI reasoning. When those assumptions are
    violated silently, the entire system becomes unsafe.
    """

    name: str

    # Assumptions this consumer makes about AI reasoning
    assumes_verified: bool = True
    assumes_step_by_step: bool = True
    assumes_high_confidence: bool = True
    min_acceptable_confidence: float = 0.7

    # What happens when assumptions are violated
    failure_mode: str = "silent"  # "silent", "error", "degraded"

    def check_assumptions(self, stage_result: StageResult) -> tuple[bool, list[str]]:
        """Check if AI reasoning meets downstream assumptions.

        Returns (assumptions_met, list_of_violations)
        """
        violations = []

        if self.assumes_verified and not stage_result.verification_performed:
            violations.append(f"Downstream '{self.name}' assumes verification, but none performed")

        if (
            self.assumes_high_confidence
            and stage_result.confidence_score < self.min_acceptable_confidence
        ):
            violations.append(
                f"Downstream '{self.name}' requires confidence >= {self.min_acceptable_confidence:.0%}, "
                f"got {stage_result.confidence_score:.0%}"
            )

        return len(violations) == 0, violations

    def execute(self, ai_output: Any) -> tuple[Any, bool]:
        """Execute downstream logic based on AI output.

        Returns (result, is_safe)
        """
        # In a real system, this would be deterministic code
        # that processes the AI's reasoning output
        return ai_output, True


class AIDecisionPipeline:
    """Multi-stage AI decision pipeline.

    Stages:
    1. INTERPRET - LLM interprets the input/problem
    2. REASON - LLM reasons through the solution
    3. VERIFY - LLM verifies its reasoning
    4. DECIDE - Downstream code makes decision based on reasoning

    This mirrors real production patterns where:
    - AI reasoning is a critical component
    - Downstream code trusts that reasoning
    - Silent degradation in reasoning quality causes silent system failures
    """

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        downstream_consumer: Optional[DownstreamConsumer] = None,
    ):
        self.config = config or PipelineConfig()
        self.downstream = downstream_consumer or DownstreamConsumer(
            name="default_consumer",
            assumes_verified=self.config.require_verification,
            assumes_step_by_step=self.config.require_step_by_step,
            assumes_high_confidence=self.config.require_confidence,
            min_acceptable_confidence=self.config.min_confidence_threshold,
        )

        # Lazy load tracer
        self._tracer = None

    @property
    def tracer(self):
        if self._tracer is None:
            from cngx.capture.tracer import CngxTracer

            self._tracer = CngxTracer(
                adapter=self.config.adapter,
                model=self.config.model,
            )
        return self._tracer

    def run(
        self,
        input_data: str,
        scenario: str = "default",
        task_id: Optional[str] = None,
    ) -> PipelineResult:
        """Run the complete pipeline.

        Args:
            input_data: The input to process
            scenario: Scenario name for tracking
            task_id: Optional task ID for cngx tracing

        Returns:
            Complete pipeline result with all stage outputs
        """
        import time

        # Create result
        result = PipelineResult(
            pipeline_id=self._generate_id(scenario),
            scenario=scenario,
            model=self.config.model,
        )

        task_id = task_id or f"pipeline_{scenario}"

        # Stage 1: INPUT
        input_stage = StageResult(
            stage=PipelineStage.INPUT,
            success=True,
            input_data=input_data,
            output_data=input_data,
            downstream_safe=True,
        )
        result.add_stage(input_stage)

        # Stage 2: INTERPRET - LLM interprets the problem
        interpret_prompt = self._build_interpret_prompt(input_data)
        interpret_result = self._run_llm_stage(
            PipelineStage.INTERPRET,
            interpret_prompt,
            task_id=f"{task_id}_interpret",
        )
        result.add_stage(interpret_result)

        if not interpret_result.success and self.config.stop_on_failure:
            result.completed = False
            return result

        # Stage 3: REASON - LLM reasons through solution
        reason_prompt = self._build_reason_prompt(
            input_data,
            interpret_result.output_data,
        )
        reason_result = self._run_llm_stage(
            PipelineStage.REASON,
            reason_prompt,
            task_id=f"{task_id}_reason",
        )
        result.add_stage(reason_result)
        result.trace_id = reason_result.raw_llm_output  # Store for cngx

        if not reason_result.success and self.config.stop_on_failure:
            result.completed = False
            return result

        # Stage 4: VERIFY - LLM verifies its work
        verify_prompt = self._build_verify_prompt(
            input_data,
            reason_result.output_data,
        )
        verify_result = self._run_llm_stage(
            PipelineStage.VERIFY,
            verify_prompt,
            task_id=f"{task_id}_verify",
        )
        result.add_stage(verify_result)

        # Stage 5: DECIDE - Downstream logic makes decision
        decide_result = self._run_decide_stage(
            verify_result,
            input_data,
        )
        result.add_stage(decide_result)

        # Check downstream assumptions
        assumptions_met, violations = self.downstream.check_assumptions(verify_result)

        if not assumptions_met:
            result.reasoning_assumptions_violated = True
            result.violated_assumptions = violations
            result.downstream_execution_safe = False
            result.downstream_risk_level = "HIGH"
        else:
            result.downstream_execution_safe = True
            result.downstream_risk_level = "LOW"

        # Final output
        result.completed = True
        result.success = decide_result.success and result.downstream_execution_safe
        result.final_answer = decide_result.output_data

        return result

    def _build_interpret_prompt(self, input_data: str) -> str:
        """Build prompt for interpretation stage."""
        return f"""Interpret the following problem. Identify:
1. What is being asked
2. What information is given
3. What approach would be appropriate

Problem: {input_data}

Provide a structured interpretation."""

    def _build_reason_prompt(self, input_data: str, interpretation: str) -> str:
        """Build prompt for reasoning stage."""
        return f"""Based on this interpretation, solve the problem step by step.

IMPORTANT: You MUST:
1. Show your work clearly with numbered steps
2. Explain your reasoning at each step
3. Be thorough - do not skip steps

Problem: {input_data}

Interpretation: {interpretation}

Solve step by step:"""

    def _build_verify_prompt(self, input_data: str, reasoning: str) -> str:
        """Build prompt for verification stage."""
        return f"""Verify the following solution. Check:
1. Are all calculations correct?
2. Is the logic sound?
3. Does the answer make sense?

IMPORTANT: You MUST explicitly verify by:
- Re-checking key calculations
- Stating whether the answer is verified
- Expressing your confidence level

Problem: {input_data}

Solution:
{reasoning}

Verification:"""

    def _run_llm_stage(
        self,
        stage: PipelineStage,
        prompt: str,
        task_id: str,
    ) -> StageResult:
        """Run an LLM stage and analyze the result."""
        import time

        start_time = time.time()

        try:
            trace = self.tracer.capture(
                prompt=prompt,
                task_id=task_id,
                save=True,
            )

            duration_ms = (time.time() - start_time) * 1000

            # Analyze the response for verification and confidence
            output = trace.output
            verification_performed = self._detect_verification(output)
            confidence_score = self._estimate_confidence(output)

            # Get fingerprint for depth analysis
            fp = self.tracer.get_fingerprint(trace.id)
            depth = fp.depth if fp else 1

            # Check downstream safety
            downstream_safe = True
            assumptions = []

            if self.config.require_verification and not verification_performed:
                downstream_safe = False
                assumptions.append("Verification was required but not performed")

            if self.config.require_step_by_step and depth < self.config.min_reasoning_depth:
                downstream_safe = False
                assumptions.append(
                    f"Reasoning depth {depth} below minimum {self.config.min_reasoning_depth}"
                )

            if (
                self.config.require_confidence
                and confidence_score < self.config.min_confidence_threshold
            ):
                downstream_safe = False
                assumptions.append(
                    f"Confidence {confidence_score:.0%} below threshold {self.config.min_confidence_threshold:.0%}"
                )

            return StageResult(
                stage=stage,
                success=True,
                input_data=prompt,
                output_data=output,
                reasoning_content=output,
                verification_performed=verification_performed,
                confidence_score=confidence_score,
                downstream_safe=downstream_safe,
                downstream_assumptions=assumptions,
                raw_llm_output=trace.id,  # Store trace ID
                duration_ms=duration_ms,
            )

        except Exception as e:
            return StageResult(
                stage=stage,
                success=False,
                input_data=prompt,
                output_data=str(e),
                downstream_safe=False,
                downstream_assumptions=[f"Stage failed: {e}"],
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _run_decide_stage(
        self,
        verify_result: StageResult,
        original_input: str,
    ) -> StageResult:
        """Run the downstream decision stage.

        This represents deterministic code that processes AI output.
        """
        # Execute downstream consumer
        output, is_safe = self.downstream.execute(verify_result.output_data)

        return StageResult(
            stage=PipelineStage.DECIDE,
            success=True,
            input_data=verify_result.output_data,
            output_data=output,
            verification_performed=verify_result.verification_performed,
            confidence_score=verify_result.confidence_score,
            downstream_safe=is_safe,
        )

    def _detect_verification(self, text: str) -> bool:
        """Detect if the LLM performed verification."""
        verification_patterns = [
            "let me verify",
            "let me check",
            "checking:",
            "verification:",
            "double-check",
            "to verify",
            "confirmed",
            "is correct",
            "verified",
            "re-checking",
            "this confirms",
        ]

        text_lower = text.lower()
        return any(pattern in text_lower for pattern in verification_patterns)

    def _estimate_confidence(self, text: str) -> float:
        """Estimate confidence level from text."""
        # High confidence markers
        high_conf = [
            "definitely",
            "certainly",
            "clearly",
            "obviously",
            "the answer is",
            "therefore",
            "thus",
            "hence",
            "verified",
            "confirmed",
            "correct",
        ]

        # Low confidence markers
        low_conf = [
            "might",
            "maybe",
            "possibly",
            "perhaps",
            "i think",
            "i believe",
            "not sure",
            "could be",
            "may be",
            "uncertain",
        ]

        text_lower = text.lower()

        high_count = sum(1 for p in high_conf if p in text_lower)
        low_count = sum(1 for p in low_conf if p in text_lower)

        # Simple heuristic
        if high_count + low_count == 0:
            return 0.5

        return high_count / (high_count + low_count + 1)

    def _generate_id(self, scenario: str) -> str:
        """Generate unique pipeline ID."""
        content = f"{scenario}:{datetime.utcnow().isoformat()}"
        return f"pipeline_{hashlib.sha256(content.encode()).hexdigest()[:12]}"
