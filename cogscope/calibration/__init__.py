"""Model-agnostic calibration — per-model behavioral profiles and adaptive thresholds.

Cogscope must work across ALL LLMs (GPT-4o, Gemini, Claude, Llama, Mistral, etc.).
Each model family has different reasoning styles:
- GPT-4o uses concise, structured reasoning
- Gemini 2.5 Flash uses verbose thinking tokens
- Claude uses <thinking> blocks with explicit self-correction
- Open-source models vary wildly

This module provides:
1. ModelProfile — behavioral baseline per model family
2. AdaptiveThresholds — thresholds that adjust based on model profiles
3. CalibrationEngine — learns profiles from observed data
"""

from cogscope.calibration.profiles import (
    AdaptiveThresholds,
    CalibrationEngine,
    ModelFamily,
    ModelProfile,
    get_adaptive_thresholds,
    get_profile,
)

__all__ = [
    "ModelProfile",
    "ModelFamily",
    "AdaptiveThresholds",
    "CalibrationEngine",
    "get_profile",
    "get_adaptive_thresholds",
]
