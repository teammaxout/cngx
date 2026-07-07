"""Cogscope System Demo - Reference AI pipeline demonstrating system-level enforcement.

This module implements a REALISTIC AI DECISION PIPELINE that:
1. Uses LLM reasoning as a critical component
2. Feeds reasoning into downstream deterministic logic
3. Shows silent failures when reasoning degrades
4. Demonstrates Cogscope's value as the ONLY protection against silent regression

This is NOT a toy demo. This mirrors real production AI systems.
"""

from cogscope.system_demo.pipeline import (
    AIDecisionPipeline,
    PipelineConfig,
    PipelineResult,
    PipelineStage,
)
from cogscope.system_demo.runner import (
    DemoResult,
    run_with_cogscope,
    run_without_cogscope,
)
from cogscope.system_demo.scenarios import (
    CodeReviewScenario,
    MathTutoringScenario,
    ResearchAnalysisScenario,
)

__all__ = [
    "AIDecisionPipeline",
    "PipelineConfig",
    "PipelineResult",
    "PipelineStage",
    "MathTutoringScenario",
    "CodeReviewScenario",
    "ResearchAnalysisScenario",
    "run_without_cogscope",
    "run_with_cogscope",
    "DemoResult",
]
