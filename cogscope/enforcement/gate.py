"""Production enforcement gate.

Multi-layer validation gate that produces hard exit codes
for CI/CD pipeline integration. Not just eval — enforcement.

Exit codes:
  0 = PASS — all checks passed
  1 = FAIL — contract violations detected
  2 = ERROR — infrastructure/configuration error
  3 = WARN — soft violations (advisory mode)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("cogscope.enforcement.gate")


class ExitCode(IntEnum):
    """Standard exit codes for enforcement gate."""

    PASS = 0
    FAIL = 1
    ERROR = 2
    WARN = 3


@dataclass
class EnforcementConfig:
    """Configuration for enforcement gate."""

    mode: str = "enforce"  # enforce | advisory | audit
    contract_paths: list[str] = field(default_factory=list)
    drift_threshold: float = 0.3
    accuracy_threshold: float = 0.8
    stability_threshold: float = 0.7
    require_consensus: bool = False
    consensus_min_models: int = 2
    fail_on_drift: bool = True
    fail_on_correctness: bool = True
    fail_on_stability: bool = True
    max_latency_ms: float = 0.0  # 0 = no limit
    output_format: str = "text"  # text | json
    report_path: Optional[str] = None


@dataclass
class CheckResult:
    """Result of a single enforcement check."""

    check_name: str
    passed: bool
    score: float
    threshold: float
    message: str
    severity: str = "error"  # error | warning | info
    details: dict = field(default_factory=dict)


@dataclass
class EnforcementResult:
    """Complete enforcement gate result."""

    exit_code: ExitCode
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    summary: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "exit_code": int(self.exit_code),
            "passed": self.passed,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "checks": [
                {
                    "check": c.check_name,
                    "passed": c.passed,
                    "score": c.score,
                    "threshold": c.threshold,
                    "message": c.message,
                    "severity": c.severity,
                }
                for c in self.checks
            ],
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def format_text(self) -> str:
        """Format result as human-readable text for CI output."""
        lines = [
            "=" * 60,
            "COGSCOPE ENFORCEMENT GATE",
            "=" * 60,
            f"Result: {'PASS ✓' if self.passed else 'FAIL ✗'}",
            f"Exit Code: {int(self.exit_code)}",
            f"Timestamp: {self.timestamp.isoformat()[:19]}",
            f"Duration: {self.duration_ms:.0f}ms",
            "-" * 60,
        ]

        for check in self.checks:
            status = "✓" if check.passed else "✗"
            lines.append(
                f"  [{status}] {check.check_name}: "
                f"{check.score:.3f} (threshold: {check.threshold:.3f}) "
                f"— {check.message}"
            )

        lines.append("-" * 60)
        lines.append(f"Summary: {self.summary}")
        lines.append("=" * 60)

        return "\n".join(lines)


class EnforcementGate:
    """Production enforcement gate for CI/CD pipelines.

    Runs multi-layer validation and produces hard exit codes.
    This is the deployment gate — not an eval tool.

    Usage:
        gate = EnforcementGate(config)
        result = gate.run(trace, fingerprint, contract)
        sys.exit(result.exit_code)
    """

    def __init__(self, config: EnforcementConfig | None = None):
        self.config = config or EnforcementConfig()

    def run(
        self,
        trace: dict | None = None,
        fingerprint: dict | None = None,
        contract_results: list[dict] | None = None,
        drift_score: float | None = None,
        benchmark_accuracy: float | None = None,
        stability_score: float | None = None,
        consensus_score: float | None = None,
        latency_ms: float | None = None,
    ) -> EnforcementResult:
        """Run enforcement gate.

        Args:
            trace: Reasoning trace dict
            fingerprint: Behavioral fingerprint dict
            contract_results: Results from contract validation
            drift_score: Drift score from drift detection
            benchmark_accuracy: Accuracy from benchmark evaluation
            stability_score: Stability score from robustness testing
            consensus_score: Consensus score from cross-model validation
            latency_ms: Response latency

        Returns:
            EnforcementResult with exit code
        """
        start = time.monotonic()
        checks: list[CheckResult] = []

        try:
            # Check 1: Contract violations
            if contract_results is not None:
                checks.append(self._check_contracts(contract_results))

            # Check 2: Drift threshold
            if drift_score is not None and self.config.fail_on_drift:
                checks.append(self._check_drift(drift_score))

            # Check 3: Correctness (benchmark accuracy)
            if benchmark_accuracy is not None and self.config.fail_on_correctness:
                checks.append(self._check_accuracy(benchmark_accuracy))

            # Check 4: Stability
            if stability_score is not None and self.config.fail_on_stability:
                checks.append(self._check_stability(stability_score))

            # Check 5: Consensus
            if consensus_score is not None and self.config.require_consensus:
                checks.append(self._check_consensus(consensus_score))

            # Check 6: Latency
            if latency_ms is not None and self.config.max_latency_ms > 0:
                checks.append(self._check_latency(latency_ms))

            # Determine exit code
            duration = (time.monotonic() - start) * 1000

            if not checks:
                return EnforcementResult(
                    exit_code=ExitCode.WARN,
                    passed=True,
                    checks=checks,
                    summary="No checks configured or no data provided",
                    duration_ms=duration,
                )

            # In advisory mode, never fail
            if self.config.mode == "advisory":
                all_passed = all(c.passed for c in checks)
                return EnforcementResult(
                    exit_code=ExitCode.PASS if all_passed else ExitCode.WARN,
                    passed=True,  # Advisory never blocks
                    checks=checks,
                    summary=self._build_summary(checks, advisory=True),
                    duration_ms=duration,
                )

            # In enforce mode, fail on any error-severity check failure
            error_failures = [c for c in checks if not c.passed and c.severity == "error"]
            warning_failures = [c for c in checks if not c.passed and c.severity == "warning"]

            if error_failures:
                return EnforcementResult(
                    exit_code=ExitCode.FAIL,
                    passed=False,
                    checks=checks,
                    summary=self._build_summary(checks),
                    duration_ms=duration,
                )
            elif warning_failures:
                return EnforcementResult(
                    exit_code=ExitCode.WARN,
                    passed=True,
                    checks=checks,
                    summary=self._build_summary(checks),
                    duration_ms=duration,
                )
            else:
                return EnforcementResult(
                    exit_code=ExitCode.PASS,
                    passed=True,
                    checks=checks,
                    summary=self._build_summary(checks),
                    duration_ms=duration,
                )

        except Exception as e:
            duration = (time.monotonic() - start) * 1000
            logger.error(f"Enforcement gate error: {e}")
            return EnforcementResult(
                exit_code=ExitCode.ERROR,
                passed=False,
                checks=checks,
                summary=f"Gate error: {e}",
                duration_ms=duration,
            )

    def _check_contracts(self, results: list[dict]) -> CheckResult:
        """Check contract validation results."""
        violations = [r for r in results if not r.get("passed", True)]
        total = len(results)
        passed_count = total - len(violations)
        score = passed_count / total if total > 0 else 1.0

        return CheckResult(
            check_name="contract_compliance",
            passed=len(violations) == 0,
            score=score,
            threshold=1.0,  # 100% compliance required
            message=(
                "All contracts satisfied"
                if not violations
                else f"{len(violations)}/{total} contract(s) violated"
            ),
            severity="error",
            details={"violations": violations[:5]},
        )

    def _check_drift(self, drift_score: float) -> CheckResult:
        """Check behavioral drift."""
        passed = drift_score <= self.config.drift_threshold
        return CheckResult(
            check_name="behavioral_drift",
            passed=passed,
            score=drift_score,
            threshold=self.config.drift_threshold,
            message=(
                f"Drift {drift_score:.3f} within threshold"
                if passed
                else f"Drift {drift_score:.3f} exceeds threshold {self.config.drift_threshold}"
            ),
            severity="error",
        )

    def _check_accuracy(self, accuracy: float) -> CheckResult:
        """Check benchmark accuracy."""
        passed = accuracy >= self.config.accuracy_threshold
        return CheckResult(
            check_name="correctness_accuracy",
            passed=passed,
            score=accuracy,
            threshold=self.config.accuracy_threshold,
            message=(
                f"Accuracy {accuracy:.1%} meets threshold"
                if passed
                else f"Accuracy {accuracy:.1%} below threshold {self.config.accuracy_threshold:.1%}"
            ),
            severity="error",
        )

    def _check_stability(self, stability: float) -> CheckResult:
        """Check robustness stability."""
        passed = stability >= self.config.stability_threshold
        return CheckResult(
            check_name="robustness_stability",
            passed=passed,
            score=stability,
            threshold=self.config.stability_threshold,
            message=(
                f"Stability {stability:.3f} meets threshold"
                if passed
                else f"Stability {stability:.3f} below threshold {self.config.stability_threshold}"
            ),
            severity="warning",
        )

    def _check_consensus(self, consensus: float) -> CheckResult:
        """Check cross-model consensus."""
        threshold = 0.7
        passed = consensus >= threshold
        return CheckResult(
            check_name="cross_model_consensus",
            passed=passed,
            score=consensus,
            threshold=threshold,
            message=(
                f"Consensus {consensus:.3f} achieved"
                if passed
                else f"Consensus {consensus:.3f} below threshold {threshold}"
            ),
            severity="warning",
        )

    def _check_latency(self, latency_ms: float) -> CheckResult:
        """Check response latency."""
        passed = latency_ms <= self.config.max_latency_ms
        return CheckResult(
            check_name="response_latency",
            passed=passed,
            score=latency_ms,
            threshold=self.config.max_latency_ms,
            message=(
                f"Latency {latency_ms:.0f}ms within limit"
                if passed
                else f"Latency {latency_ms:.0f}ms exceeds limit {self.config.max_latency_ms:.0f}ms"
            ),
            severity="warning",
        )

    def _build_summary(self, checks: list[CheckResult], advisory: bool = False) -> str:
        """Build human-readable summary."""
        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        mode = "ADVISORY" if advisory else "ENFORCE"

        if passed == total:
            return f"[{mode}] All {total} checks passed."
        else:
            failed_names = [c.check_name for c in checks if not c.passed]
            return f"[{mode}] {passed}/{total} checks passed. " f"Failed: {', '.join(failed_names)}"

    def enforce_and_exit(self, **kwargs) -> None:
        """Run gate and exit with appropriate code. For CLI usage."""
        result = self.run(**kwargs)

        if self.config.output_format == "json":
            print(result.to_json())
        else:
            print(result.format_text())

        if self.config.report_path:
            Path(self.config.report_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            Path(self.config.report_path).expanduser().write_text(result.to_json())

        sys.exit(int(result.exit_code))
