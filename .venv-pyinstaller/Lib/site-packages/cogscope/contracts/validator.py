"""Contract Validation Engine - Validates fingerprints against behavior contracts.

This is the enforcement layer. BLOCK violations halt deployment.

Security hardening:
- ReDoS protection via safe_regex_compile/safe_regex_search
- Configurable execution timeout for pattern matching
- Model-aware adaptive threshold support

Performance:
- LRU cache for compiled regex patterns (avoid re-compilation per call)
- Thread-safe pattern cache with bounded size
"""

import logging
import re
import threading
from collections import OrderedDict
from typing import Optional, Pattern

from cogscope.contracts.schema import (
    BehaviorContract,
    GateResult,
    Severity,
    Violation,
)
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace
from cogscope.security.regex_sandbox import (
    RegexComplexityError,
    RegexTimeoutError,
    safe_regex_compile,
    safe_regex_search,
)

logger = logging.getLogger("cogscope.contracts.validator")


class _PatternCache:
    """Thread-safe LRU cache for compiled regex patterns.

    Avoids recompiling the same patterns on every validation call.
    Bounded to prevent unbounded memory growth.
    """

    def __init__(self, maxsize: int = 256):
        self._cache: OrderedDict[tuple[str, int], Pattern | Exception] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get_or_compile(self, pattern: str, flags: int = 0) -> Pattern:
        """Get a compiled pattern from cache, or compile and cache it.

        Raises the same exceptions as safe_regex_compile on failure.
        Caches both successful compilations AND exceptions to avoid
        repeated recompilation of known-bad patterns.
        """
        key = (pattern, flags)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                result = self._cache[key]
                if isinstance(result, Exception):
                    raise result
                return result

        # Compile outside lock (may be slow for complex patterns)
        try:
            compiled = safe_regex_compile(pattern, flags=flags)
        except Exception as exc:
            with self._lock:
                self._cache[key] = exc
                if len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)
            raise

        with self._lock:
            self._cache[key] = compiled
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

        return compiled


# Global pattern cache shared across all validator instances
_pattern_cache = _PatternCache(maxsize=256)


class ContractValidator:
    """Validates behavioral fingerprints against contracts.

    The validator checks each constraint and produces GateResult
    for CI/CD integration. BLOCK violations set exit_code = 1.

    Performance: Uses a global LRU cache for compiled regex patterns,
    so repeated validations with the same contract are fast.
    """

    def __init__(self):
        pass

    def validate(
        self,
        fingerprint: BehavioralFingerprint,
        contract: BehaviorContract,
        trace: Optional[ReasoningTrace] = None,
    ) -> GateResult:
        """Validate a fingerprint against a contract.

        Args:
            fingerprint: The behavioral fingerprint to validate
            contract: The contract to validate against
            trace: Optional trace for pattern checking

        Returns:
            GateResult with all violations and deployment decision
        """
        violations = []

        # Check each constraint type
        if contract.depth:
            violations.extend(self._check_depth(fingerprint, contract))

        if contract.steps:
            violations.extend(self._check_steps(fingerprint, contract))

        if contract.verification:
            violations.extend(self._check_verification(fingerprint, contract))

        if contract.tools:
            violations.extend(self._check_tools(fingerprint, contract))

        if contract.uncertainty:
            violations.extend(self._check_uncertainty(fingerprint, contract))

        if contract.output:
            violations.extend(self._check_output(fingerprint, contract))

        if contract.forbidden_patterns and trace:
            violations.extend(self._check_forbidden_patterns(trace, contract))

        if contract.required_patterns and trace:
            violations.extend(self._check_required_patterns(trace, contract))

        # Count by severity
        warn_count = sum(1 for v in violations if v.severity == Severity.WARN)
        fail_count = sum(1 for v in violations if v.severity == Severity.FAIL)
        block_count = sum(1 for v in violations if v.severity == Severity.BLOCK)

        # Determine gate decision
        blocked = block_count > 0 and contract.block_on_violation
        passed = block_count == 0 and fail_count == 0

        # Exit code for CI/CD
        exit_code = 0
        if blocked:
            exit_code = 1  # Hard block
        elif fail_count > 0:
            exit_code = 2  # Soft fail (overridable)

        return GateResult(
            contract_name=contract.name,
            contract_version=contract.version,
            contract_hash=contract.get_hash(),
            trace_id=fingerprint.trace_id,
            model=fingerprint.model,
            task_id=fingerprint.task_id,
            passed=passed,
            blocked=blocked,
            violations=violations,
            block_count=block_count,
            fail_count=fail_count,
            warn_count=warn_count,
            exit_code=exit_code,
        )

    def _check_depth(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check depth constraints."""
        violations = []
        depth = contract.depth

        if depth.min is not None and fp.depth < depth.min:
            violations.append(
                Violation(
                    constraint="depth.min",
                    severity=depth.severity,
                    message=f"Reasoning depth {fp.depth} is below minimum {depth.min}",
                    expected=f">= {depth.min}",
                    actual=fp.depth,
                    rationale=depth.rationale
                    or "Shallow reasoning indicates capability regression",
                )
            )

        if depth.max is not None and fp.depth > depth.max:
            violations.append(
                Violation(
                    constraint="depth.max",
                    severity=depth.severity,
                    message=f"Reasoning depth {fp.depth} exceeds maximum {depth.max}",
                    expected=f"<= {depth.max}",
                    actual=fp.depth,
                    rationale=depth.rationale or "Excessive depth may indicate runaway reasoning",
                )
            )

        return violations

    def _check_steps(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check steps constraints."""
        violations = []
        steps = contract.steps

        if steps.min is not None and fp.total_steps < steps.min:
            violations.append(
                Violation(
                    constraint="steps.min",
                    severity=steps.severity,
                    message=f"Total steps {fp.total_steps} is below minimum {steps.min}",
                    expected=f">= {steps.min}",
                    actual=fp.total_steps,
                    rationale=steps.rationale or "Insufficient reasoning steps for this domain",
                )
            )

        if steps.max is not None and fp.total_steps > steps.max:
            violations.append(
                Violation(
                    constraint="steps.max",
                    severity=steps.severity,
                    message=f"Total steps {fp.total_steps} exceeds maximum {steps.max}",
                    expected=f"<= {steps.max}",
                    actual=fp.total_steps,
                    rationale=steps.rationale
                    or "Too many steps may indicate inefficient reasoning",
                )
            )

        return violations

    def _check_verification(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check verification constraints."""
        violations = []
        ver = contract.verification

        if ver.required and fp.verification_steps == 0:
            violations.append(
                Violation(
                    constraint="verification.required",
                    severity=ver.severity,
                    message="VERIFICATION REQUIRED but none detected",
                    expected="At least 1 verification step",
                    actual=0,
                    rationale=ver.rationale,
                )
            )

        if ver.min_steps > 0 and fp.verification_steps < ver.min_steps:
            violations.append(
                Violation(
                    constraint="verification.min_steps",
                    severity=ver.severity,
                    message=f"Found {fp.verification_steps} verification steps, need at least {ver.min_steps}",
                    expected=f">= {ver.min_steps}",
                    actual=fp.verification_steps,
                    rationale=ver.rationale,
                )
            )

        return violations

    def _check_tools(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check tool usage constraints."""
        violations = []
        tools = contract.tools
        tool_sequence = fp.tool_call_sequence or []

        if tools.required:
            for required_tool in tools.required:
                if required_tool not in tool_sequence:
                    violations.append(
                        Violation(
                            constraint="tools.required",
                            severity=tools.severity,
                            message=f"Required tool '{required_tool}' was not called",
                            expected=f"Tool '{required_tool}' must be used",
                            actual=f"Used: {tool_sequence}",
                            rationale=tools.rationale,
                        )
                    )

        if tools.forbidden:
            for forbidden_tool in tools.forbidden:
                if forbidden_tool in tool_sequence:
                    violations.append(
                        Violation(
                            constraint="tools.forbidden",
                            severity=tools.severity,
                            message=f"Forbidden tool '{forbidden_tool}' was called",
                            expected=f"Tool '{forbidden_tool}' must not be used",
                            actual=f"Used: {tool_sequence}",
                            rationale=tools.rationale,
                        )
                    )

        if tools.max_calls is not None and fp.tool_call_count > tools.max_calls:
            violations.append(
                Violation(
                    constraint="tools.max_calls",
                    severity=tools.severity,
                    message=f"Tool call count {fp.tool_call_count} exceeds maximum {tools.max_calls}",
                    expected=f"<= {tools.max_calls}",
                    actual=fp.tool_call_count,
                    rationale=tools.rationale,
                )
            )

        if tools.min_diversity is not None and fp.tool_diversity < tools.min_diversity:
            violations.append(
                Violation(
                    constraint="tools.min_diversity",
                    severity=tools.severity,
                    message=f"Tool diversity {fp.tool_diversity:.2f} is below minimum {tools.min_diversity}",
                    expected=f">= {tools.min_diversity}",
                    actual=fp.tool_diversity,
                    rationale=tools.rationale,
                )
            )

        return violations

    def _check_uncertainty(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check uncertainty constraints."""
        violations = []
        unc = contract.uncertainty

        if unc.max_hedging_ratio is not None and fp.hedging_ratio > unc.max_hedging_ratio:
            violations.append(
                Violation(
                    constraint="uncertainty.max_hedging_ratio",
                    severity=unc.severity,
                    message=f"Hedging ratio {fp.hedging_ratio:.2f} exceeds maximum {unc.max_hedging_ratio}",
                    expected=f"<= {unc.max_hedging_ratio}",
                    actual=round(fp.hedging_ratio, 2),
                    rationale=unc.rationale or "Excessive hedging indicates low confidence",
                )
            )

        if (
            unc.min_confidence_markers is not None
            and fp.confidence_markers < unc.min_confidence_markers
        ):
            violations.append(
                Violation(
                    constraint="uncertainty.min_confidence_markers",
                    severity=unc.severity,
                    message=f"Found {fp.confidence_markers} confidence markers, need at least {unc.min_confidence_markers}",
                    expected=f">= {unc.min_confidence_markers}",
                    actual=fp.confidence_markers,
                    rationale=unc.rationale,
                )
            )

        if (
            unc.max_uncertainty_markers is not None
            and fp.uncertainty_markers > unc.max_uncertainty_markers
        ):
            violations.append(
                Violation(
                    constraint="uncertainty.max_uncertainty_markers",
                    severity=unc.severity,
                    message=f"Found {fp.uncertainty_markers} uncertainty markers, maximum is {unc.max_uncertainty_markers}",
                    expected=f"<= {unc.max_uncertainty_markers}",
                    actual=fp.uncertainty_markers,
                    rationale=unc.rationale,
                )
            )

        return violations

    def _check_output(
        self,
        fp: BehavioralFingerprint,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check output constraints."""
        violations = []
        out = contract.output

        if out.min_length is not None and fp.output_length < out.min_length:
            violations.append(
                Violation(
                    constraint="output.min_length",
                    severity=out.severity,
                    message=f"Output length {fp.output_length} is below minimum {out.min_length}",
                    expected=f">= {out.min_length}",
                    actual=fp.output_length,
                    rationale=out.rationale,
                )
            )

        if out.max_length is not None and fp.output_length > out.max_length:
            violations.append(
                Violation(
                    constraint="output.max_length",
                    severity=out.severity,
                    message=f"Output length {fp.output_length} exceeds maximum {out.max_length}",
                    expected=f"<= {out.max_length}",
                    actual=fp.output_length,
                    rationale=out.rationale,
                )
            )

        if out.require_structured and not fp.structured_output:
            violations.append(
                Violation(
                    constraint="output.require_structured",
                    severity=out.severity,
                    message="Structured output required but not detected",
                    expected=True,
                    actual=False,
                    rationale=out.rationale,
                )
            )

        return violations

    def _check_forbidden_patterns(
        self,
        trace: ReasoningTrace,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check forbidden pattern constraints with ReDoS protection."""
        violations = []

        for fp in contract.forbidden_patterns:
            try:
                pattern = _pattern_cache.get_or_compile(fp.pattern, flags=re.IGNORECASE)
            except (RegexComplexityError, Exception) as e:
                logger.warning(f"Skipping dangerous/invalid forbidden pattern '{fp.pattern}': {e}")
                violations.append(
                    Violation(
                        constraint="forbidden_pattern",
                        severity=Severity.WARN,
                        message=f"Pattern could not be compiled safely: {fp.description or fp.pattern[:50]}",
                        expected="Valid, safe regex pattern",
                        actual=str(e)[:200],
                        rationale="Contract contains an invalid or potentially dangerous regex pattern",
                    )
                )
                continue

            if fp.check_output and trace.output:
                try:
                    if safe_regex_search(pattern, trace.output):
                        violations.append(
                            Violation(
                                constraint="forbidden_pattern",
                                severity=fp.severity,
                                message=f"FORBIDDEN PATTERN DETECTED: {fp.description or fp.pattern}",
                                expected=f"Pattern '{fp.pattern}' must not appear",
                                actual="Pattern found in output",
                                rationale=fp.rationale,
                            )
                        )
                except RegexTimeoutError:
                    logger.warning(f"Forbidden pattern timed out on output: {fp.pattern[:50]}")

            if fp.check_reasoning and trace.reasoning_content:
                try:
                    if safe_regex_search(pattern, trace.reasoning_content):
                        violations.append(
                            Violation(
                                constraint="forbidden_pattern",
                                severity=fp.severity,
                                message=f"FORBIDDEN PATTERN IN REASONING: {fp.description or fp.pattern}",
                                expected=f"Pattern '{fp.pattern}' must not appear",
                                actual="Pattern found in reasoning",
                                rationale=fp.rationale,
                            )
                        )
                except RegexTimeoutError:
                    logger.warning(f"Forbidden pattern timed out on reasoning: {fp.pattern[:50]}")

        return violations

    def _check_required_patterns(
        self,
        trace: ReasoningTrace,
        contract: BehaviorContract,
    ) -> list[Violation]:
        """Check required pattern constraints with ReDoS protection."""
        violations = []

        for rp in contract.required_patterns:
            try:
                pattern = _pattern_cache.get_or_compile(rp.pattern, flags=re.IGNORECASE)
            except (RegexComplexityError, Exception) as e:
                logger.warning(f"Skipping dangerous/invalid required pattern '{rp.pattern}': {e}")
                violations.append(
                    Violation(
                        constraint="required_pattern",
                        severity=Severity.WARN,
                        message=f"Pattern could not be compiled safely: {rp.description or rp.pattern[:50]}",
                        expected="Valid, safe regex pattern",
                        actual=str(e)[:200],
                        rationale="Contract contains an invalid or potentially dangerous regex pattern",
                    )
                )
                continue

            found = False

            if rp.check_output and trace.output:
                try:
                    if safe_regex_search(pattern, trace.output):
                        found = True
                except RegexTimeoutError:
                    logger.warning(f"Required pattern timed out on output: {rp.pattern[:50]}")

            if rp.check_reasoning and trace.reasoning_content:
                try:
                    if safe_regex_search(pattern, trace.reasoning_content):
                        found = True
                except RegexTimeoutError:
                    logger.warning(f"Required pattern timed out on reasoning: {rp.pattern[:50]}")

            if not found:
                violations.append(
                    Violation(
                        constraint="required_pattern",
                        severity=rp.severity,
                        message=f"REQUIRED PATTERN MISSING: {rp.description or rp.pattern}",
                        expected=f"Pattern '{rp.pattern}' must appear",
                        actual="Pattern not found",
                        rationale=rp.rationale,
                    )
                )

        return violations


class DeploymentGate:
    """Deployment gate for CI/CD integration.

    This is the primary interface for blocking deployments.
    """

    def __init__(self):
        self.validator = ContractValidator()

    def check(
        self,
        fingerprint: BehavioralFingerprint,
        contract: BehaviorContract,
        trace: Optional[ReasoningTrace] = None,
    ) -> GateResult:
        """Check if deployment should be allowed.

        Returns GateResult with exit_code for CI/CD.
        """
        return self.validator.validate(fingerprint, contract, trace)

    def check_and_exit(
        self,
        fingerprint: BehavioralFingerprint,
        contract: BehaviorContract,
        trace: Optional[ReasoningTrace] = None,
    ) -> None:
        """Check and exit with appropriate code.

        For use in CI/CD pipelines.
        """
        import sys

        result = self.check(fingerprint, contract, trace)
        print(result.report())
        sys.exit(result.exit_code)


def validate_contract(
    fingerprint: BehavioralFingerprint,
    contract: BehaviorContract,
    trace: Optional[ReasoningTrace] = None,
) -> GateResult:
    """Convenience function to validate a fingerprint against a contract."""
    validator = ContractValidator()
    return validator.validate(fingerprint, contract, trace)
