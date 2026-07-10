"""
cngx, local LLM reasoning fingerprinting and policy checks.

Capture reasoning traces, extract behavioral fingerprints, validate YAML
policies, detect drift, and gate agent output in CI.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.2.0"
__author__ = "cngx Contributors"

# Keep the public surface, but import heavy modules lazily so CLI entrypoints
# (and PyInstaller binaries) can resolve --help / version without pulling the
# full dependency graph at module import time.
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

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "ConfidenceCalibrator": ("cngx.calibration.confidence", "ConfidenceCalibrator"),
    "StreamChunk": ("cngx.capture.adapters.base", "StreamChunk"),
    "CngxTracer": ("cngx.capture.tracer", "CngxTracer"),
    "Baseline": ("cngx.core.models", "Baseline"),
    "BehavioralFingerprint": ("cngx.core.models", "BehavioralFingerprint"),
    "BehaviorChange": ("cngx.core.models", "BehaviorChange"),
    "BehaviorDiff": ("cngx.core.models", "BehaviorDiff"),
    "DriftReport": ("cngx.core.models", "DriftReport"),
    "EvalResult": ("cngx.core.models", "EvalResult"),
    "ReasoningTrace": ("cngx.core.models", "ReasoningTrace"),
    "DiffEngine": ("cngx.diff.engine", "DiffEngine"),
    "DriftDetector": ("cngx.drift.detector", "DriftDetector"),
    "EnforcementGate": ("cngx.enforcement", "EnforcementGate"),
    "GitHubActionGenerator": ("cngx.enforcement", "GitHubActionGenerator"),
    "FingerprintExtractor": ("cngx.fingerprint.extractor", "FingerprintExtractor"),
    "ProviderConfig": ("cngx.providers", "ProviderConfig"),
    "RateLimiter": ("cngx.providers", "RateLimiter"),
    "RetryConfig": ("cngx.providers", "RetryConfig"),
    "retry_with_backoff": ("cngx.providers", "retry_with_backoff"),
    "BaselineManager": ("cngx.versioning.baseline", "BaselineManager"),
    "PinningManager": ("cngx.versioning.pinning", "PinningManager"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value
