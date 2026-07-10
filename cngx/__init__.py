"""
cngx, local LLM reasoning fingerprinting and policy checks.

Capture reasoning traces, extract behavioral fingerprints, validate YAML
policies, detect drift, and gate agent output in CI.
"""

__version__ = "0.1.4"
__author__ = "cngx Contributors"

from cngx.calibration.confidence import ConfidenceCalibrator
from cngx.capture.adapters.base import StreamChunk
from cngx.capture.tracer import CngxTracer
from cngx.core.models import (
    Baseline,
    BehavioralFingerprint,
    BehaviorChange,
    BehaviorDiff,
    DriftReport,
    EvalResult,
    ReasoningTrace,
)
from cngx.diff.engine import DiffEngine
from cngx.drift.detector import DriftDetector
from cngx.enforcement import EnforcementGate, GitHubActionGenerator
from cngx.fingerprint.extractor import FingerprintExtractor
from cngx.providers import ProviderConfig, RateLimiter, RetryConfig, retry_with_backoff
from cngx.versioning.baseline import BaselineManager
from cngx.versioning.pinning import PinningManager

__all__ = [
    "__version__",
    "ReasoningTrace",
    "BehavioralFingerprint",
    "BehaviorDiff",
    "BehaviorChange",
    "Baseline",
    "DriftReport",
    "EvalResult",
    "CngxTracer",
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
