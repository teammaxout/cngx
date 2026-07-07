"""
Cogscope — behavioral contract enforcement for LLM systems.

Capture reasoning traces, extract behavioral fingerprints, validate YAML
contracts, detect drift, and gate deployments in CI/CD.
"""

__version__ = "0.1.0"
__author__ = "Cogscope Contributors"

from cogscope.calibration.confidence import ConfidenceCalibrator
from cogscope.capture.adapters.base import StreamChunk
from cogscope.capture.tracer import CogscopeTracer
from cogscope.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorChange,
    BehaviorDiff,
    DriftReport,
    EvalResult,
    ReasoningTrace,
)
from cogscope.diff.engine import DiffEngine
from cogscope.drift.detector import DriftDetector
from cogscope.enforcement import EnforcementGate, GitHubActionGenerator
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.providers import ProviderConfig, RateLimiter, RetryConfig, retry_with_backoff
from cogscope.versioning.baseline import BaselineManager
from cogscope.versioning.pinning import PinningManager

__all__ = [
    "__version__",
    "ReasoningTrace",
    "BehavioralFingerprint",
    "BehaviorDiff",
    "BehaviorChange",
    "Baseline",
    "DriftReport",
    "EvalResult",
    "CogscopeTracer",
    "StreamChunk",
    "FingerprintExtractor",
    "DiffEngine",
    "DriftDetector",
    "BaselineManager",
    "PinningManager",
    "ProviderConfig",
    "RateLimiter",
    "RetryConfig",
    "retry_with_backoff",
    "ConfidenceCalibrator",
    "EnforcementGate",
    "GitHubActionGenerator",
]
