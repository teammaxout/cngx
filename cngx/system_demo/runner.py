"""Demo Runner - Executes scenarios with and without cngx protection.

This is the core demonstration: showing the contrast between
running a system WITH cngx protection vs WITHOUT it.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from cngx.contracts import BehaviorContract, DeploymentGate, GateResult
from cngx.system_demo.pipeline import (
    AIDecisionPipeline,
    PipelineConfig,
    PipelineResult,
)
from cngx.system_demo.scenarios import Scenario


class DemoMode(str, Enum):
    """Demo execution mode."""

    WITHOUT_cngx = "without_cngx"
    WITH_cngx = "with_cngx"


class DemoResult(BaseModel):
    """Result from a demo run."""

    mode: DemoMode
    scenario_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Pipeline result
    pipeline_result: Optional[PipelineResult] = None

    # cngx gate result (only for WITH_cngx mode)
    gate_result: Optional[GateResult] = None

    # Key outcomes
    pipeline_completed: bool = False
    reasoning_assumptions_violated: bool = False
    downstream_would_execute: bool = False
    downstream_is_safe: bool = False
    cngx_blocked: bool = False

    # Timing
    duration_ms: float = 0.0

    # The dangerous outcome (for WITHOUT_cngx)
    silent_failure: bool = False
    silent_failure_description: str = ""

    def to_summary(self) -> dict:
        """Summary for display."""
        return {
            "mode": self.mode.value,
            "scenario": self.scenario_name,
            "completed": self.pipeline_completed,
            "assumptions_violated": self.reasoning_assumptions_violated,
            "downstream_would_execute": self.downstream_would_execute,
            "downstream_safe": self.downstream_is_safe,
            "cngx_blocked": self.cngx_blocked,
            "silent_failure": self.silent_failure,
            "duration_ms": self.duration_ms,
        }


def run_without_cngx(scenario: Scenario) -> DemoResult:
    """Run a scenario WITHOUT cngx protection.

    This shows what happens in production AI systems today:
    - AI reasoning is captured
    - Downstream code executes based on that reasoning
    - If reasoning quality degraded, failure is SILENT

    The system appears to work. Metrics look fine.
    But reasoning assumptions are violated.
    """
    start_time = time.time()

    # Create pipeline with scenario config
    pipeline = AIDecisionPipeline(
        config=scenario.pipeline_config,
        downstream_consumer=scenario.downstream_consumer,
    )

    # Run pipeline
    pipeline_result = pipeline.run(
        input_data=scenario.problem,
        scenario=scenario.name,
    )

    duration_ms = (time.time() - start_time) * 1000

    # Determine if silent failure occurred
    silent_failure = (
        pipeline_result.completed  # Pipeline ran successfully
        and pipeline_result.reasoning_assumptions_violated  # But assumptions violated
        and pipeline_result.downstream_would_execute  # And downstream would still run
    )

    silent_failure_desc = ""
    if silent_failure:
        silent_failure_desc = (
            f"Pipeline completed with output, but reasoning assumptions were violated: "
            f"{', '.join(pipeline_result.violated_assumptions)}. "
            f"Downstream consumer '{scenario.downstream_consumer.name}' would execute "
            f"with degraded reasoning (failure_mode='{scenario.downstream_consumer.failure_mode}')."
        )

    return DemoResult(
        mode=DemoMode.WITHOUT_cngx,
        scenario_name=scenario.name,
        pipeline_result=pipeline_result,
        pipeline_completed=pipeline_result.completed,
        reasoning_assumptions_violated=pipeline_result.reasoning_assumptions_violated,
        downstream_would_execute=True,  # WITHOUT cngx, downstream ALWAYS executes
        downstream_is_safe=pipeline_result.downstream_execution_safe,
        cngx_blocked=False,  # No cngx to block
        duration_ms=duration_ms,
        silent_failure=silent_failure,
        silent_failure_description=silent_failure_desc,
    )


def run_with_cngx(scenario: Scenario) -> DemoResult:
    """Run a scenario WITH cngx protection.

    This shows how cngx changes the equation:
    - AI reasoning is captured
    - cngx validates reasoning against contract BEFORE downstream execution
    - If contract violated, deployment is BLOCKED
    - Silent failures become explicit failures

    The key insight: WITH cngx, you can't silently ship bad reasoning.
    """
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import ContractValidator

    start_time = time.time()

    # First, capture the reasoning trace directly
    tracer = CngxTracer(
        adapter=scenario.pipeline_config.adapter,
        model=scenario.pipeline_config.model,
    )

    # Build a comprehensive prompt that captures the full pipeline behavior
    prompt = f"""You are part of a critical AI system: {scenario.name}

{scenario.description}

TASK: {scenario.problem}

You MUST:
1. Interpret the problem clearly
2. Reason through the solution step by step
3. VERIFY your answer by checking your work
4. State your final answer with confidence

Be thorough. This output feeds into downstream systems that trust your reasoning."""

    # Capture trace
    trace = tracer.capture(
        prompt=prompt,
        task_id=f"cngx_demo_{scenario.scenario_type.value}",
        save=True,
    )

    # Get fingerprint
    fp = tracer.get_fingerprint(trace.id)

    # Run cngx gate
    gate = DeploymentGate()
    gate_result = gate.check(fp, scenario.contract, trace)

    # Create pipeline result for comparison
    pipeline_result = PipelineResult(
        pipeline_id=f"cngx_{trace.id}",
        scenario=scenario.name,
        model=scenario.pipeline_config.model,
        completed=True,
        success=not gate_result.blocked,
        trace_id=trace.id,
        cngx_blocked=gate_result.blocked,
        cngx_violations=[v.model_dump() for v in gate_result.violations],
        final_answer=trace.output[:500] if trace.output else None,
    )

    # Check if assumptions would have been violated
    assumptions_violated = any(v.severity.value == "block" for v in gate_result.violations)

    duration_ms = (time.time() - start_time) * 1000

    return DemoResult(
        mode=DemoMode.WITH_cngx,
        scenario_name=scenario.name,
        pipeline_result=pipeline_result,
        gate_result=gate_result,
        pipeline_completed=True,
        reasoning_assumptions_violated=assumptions_violated,
        downstream_would_execute=not gate_result.blocked,  # Only if not blocked
        downstream_is_safe=not gate_result.blocked and gate_result.passed,
        cngx_blocked=gate_result.blocked,
        duration_ms=duration_ms,
        silent_failure=False,  # WITH cngx, failures are never silent
        silent_failure_description="",
    )


class DemoComparison(BaseModel):
    """Comparison of WITH vs WITHOUT cngx."""

    scenario_name: str

    without_cngx: DemoResult
    with_cngx: DemoResult

    # Key insights
    silent_failure_prevented: bool = False
    deployment_would_have_shipped: bool = False
    downstream_protected: bool = False

    def generate_report(self) -> str:
        """Generate human-readable comparison report."""
        lines = [
            "=" * 70,
            f"SCENARIO: {self.scenario_name}",
            "=" * 70,
            "",
            "─" * 70,
            "WITHOUT cngx:",
            "─" * 70,
            f"  Pipeline completed: {self.without_cngx.pipeline_completed}",
            f"  Reasoning assumptions violated: {self.without_cngx.reasoning_assumptions_violated}",
            f"  Downstream would execute: {self.without_cngx.downstream_would_execute}",
            f"  Downstream is safe: {self.without_cngx.downstream_is_safe}",
            f"  SILENT FAILURE: {self.without_cngx.silent_failure}",
        ]

        if self.without_cngx.silent_failure:
            lines.extend(
                [
                    "",
                    f"  ⚠️  {self.without_cngx.silent_failure_description}",
                ]
            )

        lines.extend(
            [
                "",
                "─" * 70,
                "WITH cngx:",
                "─" * 70,
                f"  Pipeline completed: {self.with_cngx.pipeline_completed}",
                f"  cngx Gate BLOCKED: {self.with_cngx.cngx_blocked}",
                f"  Downstream would execute: {self.with_cngx.downstream_would_execute}",
                f"  Downstream is safe: {self.with_cngx.downstream_is_safe}",
            ]
        )

        if self.with_cngx.gate_result:
            lines.extend(
                [
                    "",
                    f"  cngx Exit Code: {self.with_cngx.gate_result.exit_code}",
                    "  Violations:",
                ]
            )
            for v in self.with_cngx.gate_result.violations[:5]:
                lines.append(f"    [{v.severity.value.upper()}] {v.message}")

        lines.extend(
            [
                "",
                "─" * 70,
                "ANALYSIS:",
                "─" * 70,
            ]
        )

        if self.silent_failure_prevented:
            lines.append("  ✓ SILENT FAILURE PREVENTED by cngx")

        if self.deployment_would_have_shipped:
            lines.append("  ✓ BAD DEPLOYMENT WOULD HAVE SHIPPED without cngx")

        if self.downstream_protected:
            lines.append("  ✓ DOWNSTREAM SYSTEMS PROTECTED by cngx gate")

        lines.extend(
            [
                "",
                "=" * 70,
            ]
        )

        return "\n".join(lines)


def run_comparison(scenario: Scenario) -> DemoComparison:
    """Run a full comparison: WITHOUT cngx vs WITH cngx.

    This is the key demonstration. Shows:
    1. What happens without protection (silent failure)
    2. What happens with protection (explicit blocking)
    3. Why the difference matters
    """
    # Run both modes
    without_result = run_without_cngx(scenario)
    with_result = run_with_cngx(scenario)

    # Analyze
    silent_failure_prevented = without_result.silent_failure and with_result.cngx_blocked

    deployment_would_have_shipped = (
        without_result.downstream_would_execute and without_result.reasoning_assumptions_violated
    )

    downstream_protected = (
        with_result.cngx_blocked and without_result.reasoning_assumptions_violated
    )

    return DemoComparison(
        scenario_name=scenario.name,
        without_cngx=without_result,
        with_cngx=with_result,
        silent_failure_prevented=silent_failure_prevented,
        deployment_would_have_shipped=deployment_would_have_shipped,
        downstream_protected=downstream_protected,
    )
