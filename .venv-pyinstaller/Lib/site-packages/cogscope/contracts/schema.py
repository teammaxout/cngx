"""Behavior Contracts - Machine-readable specifications for AI reasoning invariants.

Cogscope Behavior Contracts define HARD CONSTRAINTS on how AI systems must reason.
Violations at BLOCK severity prevent deployment.

This is not observability. This is enforcement.
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Violation severity levels.

    WARN: Log but continue - minor deviation
    FAIL: Report failure but allow override
    BLOCK: Hard stop - deployment MUST be prevented
    """

    WARN = "warn"
    FAIL = "fail"
    BLOCK = "block"


class DomainIntent(str, Enum):
    """Domain for which this contract is designed."""

    MATH = "math"
    RESEARCH = "research"
    CODE = "code"
    LOGIC = "logic"
    GENERAL = "general"
    SAFETY_CRITICAL = "safety_critical"


class DepthConstraint(BaseModel):
    """Constraints on reasoning depth.

    Shallow reasoning in complex domains indicates capability regression.
    """

    min: Optional[int] = Field(None, description="Minimum reasoning depth required")
    max: Optional[int] = Field(None, description="Maximum reasoning depth allowed")
    severity: Severity = Severity.FAIL
    rationale: str = Field("", description="Why this constraint exists")


class StepsConstraint(BaseModel):
    """Constraints on reasoning steps.

    Step count bounds ensure thorough analysis without runaway loops.
    """

    min: Optional[int] = Field(None, description="Minimum total steps required")
    max: Optional[int] = Field(None, description="Maximum total steps allowed")
    severity: Severity = Severity.FAIL
    rationale: str = Field("", description="Why this constraint exists")


class VerificationConstraint(BaseModel):
    """Requirements for self-verification.

    Critical for math, code, and safety domains where errors compound.
    """

    required: bool = Field(False, description="Must include verification steps")
    min_steps: int = Field(0, description="Minimum verification steps required")
    severity: Severity = Severity.BLOCK
    rationale: str = Field(
        "Self-verification catches errors before they propagate",
        description="Why this constraint exists",
    )


class ToolConstraint(BaseModel):
    """Constraints on tool usage.

    Ensures models use required capabilities and avoid dangerous tools.
    """

    required: Optional[list[str]] = Field(None, description="Tools that must be called")
    forbidden: Optional[list[str]] = Field(None, description="Tools that must not be called")
    max_calls: Optional[int] = Field(None, description="Maximum total tool calls")
    min_diversity: Optional[float] = Field(None, description="Minimum tool diversity (0-1)")
    severity: Severity = Severity.FAIL
    rationale: str = Field("", description="Why this constraint exists")


class UncertaintyConstraint(BaseModel):
    """Constraints on uncertainty expression.

    Excessive hedging indicates lack of confidence or capability regression.
    """

    max_hedging_ratio: Optional[float] = Field(None, description="Maximum hedging ratio (0-1)")
    min_confidence_markers: Optional[int] = Field(None, description="Minimum confidence markers")
    max_uncertainty_markers: Optional[int] = Field(None, description="Maximum uncertainty markers")
    severity: Severity = Severity.WARN
    rationale: str = Field("", description="Why this constraint exists")


class OutputConstraint(BaseModel):
    """Constraints on output characteristics."""

    min_length: Optional[int] = Field(None, description="Minimum output length (chars)")
    max_length: Optional[int] = Field(None, description="Maximum output length (chars)")
    require_structured: bool = Field(False, description="Must produce structured output")
    severity: Severity = Severity.FAIL
    rationale: str = Field("", description="Why this constraint exists")


class ForbiddenPattern(BaseModel):
    """A pattern that must not appear in reasoning.

    Catches dangerous outputs, hallucination patterns, or capability leaks.
    """

    pattern: str = Field(..., description="Regex pattern to forbid")
    description: str = Field("", description="Why this pattern is forbidden")
    check_output: bool = Field(True, description="Check in output")
    check_reasoning: bool = Field(True, description="Check in reasoning content")
    severity: Severity = Severity.BLOCK
    rationale: str = Field("", description="What happens if this appears")


class RequiredPattern(BaseModel):
    """A pattern that must appear in reasoning.

    Ensures critical reasoning elements are present.
    """

    pattern: str = Field(..., description="Regex pattern required")
    description: str = Field("", description="Why this pattern is required")
    check_output: bool = Field(True, description="Check in output")
    check_reasoning: bool = Field(False, description="Check in reasoning content")
    severity: Severity = Severity.FAIL
    rationale: str = Field("", description="What happens if missing")


class BehaviorContract(BaseModel):
    """Machine-readable specification of AI reasoning invariants.

    A contract defines HARD CONSTRAINTS that AI reasoning must satisfy.
    BLOCK-level violations prevent deployment.

    Contracts are:
    - Deterministic: Same input → same validation result
    - Versionable: Tracked and diffable over time
    - Enforceable: Violations block CI/CD pipelines
    """

    # Identity
    name: str = Field(..., description="Unique contract identifier")
    version: str = Field("1.0.0", description="Semantic version")
    description: str = Field("", description="What this contract enforces")

    # Domain and intent
    domain: DomainIntent = Field(DomainIntent.GENERAL, description="Target domain")
    intent: str = Field("", description="High-level goal of this contract")

    # Ownership
    author: str = Field("", description="Contract author/team")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Scope
    task_ids: Optional[list[str]] = Field(None, description="Apply to specific tasks only")
    models: Optional[list[str]] = Field(None, description="Apply to specific models only")

    # Structural constraints
    depth: Optional[DepthConstraint] = Field(None, description="Reasoning depth bounds")
    steps: Optional[StepsConstraint] = Field(None, description="Reasoning steps bounds")

    # Verification requirements
    verification: Optional[VerificationConstraint] = Field(
        None, description="Self-verification requirements"
    )

    # Tool usage rules
    tools: Optional[ToolConstraint] = Field(None, description="Tool usage constraints")

    # Uncertainty handling
    uncertainty: Optional[UncertaintyConstraint] = Field(
        None, description="Uncertainty expression limits"
    )

    # Output constraints
    output: Optional[OutputConstraint] = Field(None, description="Output characteristics")

    # Pattern rules
    forbidden_patterns: list[ForbiddenPattern] = Field(default_factory=list)
    required_patterns: list[RequiredPattern] = Field(default_factory=list)

    # Enforcement
    block_on_violation: bool = Field(True, description="Block deployment on any BLOCK violation")

    def get_hash(self) -> str:
        """Get deterministic hash of contract for versioning.

        Cached after first computation, contracts are typically immutable
        after loading, so the hash doesn't change.
        """
        # Use object __dict__ for caching (avoids Pydantic field restriction)
        cached = self.__dict__.get("__hash_cache")
        if cached is not None:
            return cached
        content = self.model_dump_json(exclude={"created_at"})
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        self.__dict__["__hash_cache"] = h
        return h

    @classmethod
    def from_yaml(cls, path: Path) -> "BehaviorContract":
        """Load contract from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def from_json(cls, path: Path) -> "BehaviorContract":
        """Load contract from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def to_yaml(self, path: Optional[Path] = None) -> str:
        """Export contract to YAML."""
        data = self.model_dump(mode="json", exclude_none=True)
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)
        if path:
            with open(path, "w") as f:
                f.write(yaml_str)
        return yaml_str

    def to_json(self, path: Optional[Path] = None) -> str:
        """Export contract to JSON."""
        json_str = self.model_dump_json(indent=2, exclude_none=True)
        if path:
            with open(path, "w") as f:
                f.write(json_str)
        return json_str

    def applies_to(self, task_id: str, model: str) -> bool:
        """Check if this contract applies to a given task and model."""
        if self.task_ids and task_id not in self.task_ids:
            return False
        if self.models and model not in self.models:
            return False
        return True


class Violation(BaseModel):
    """A single contract violation.

    BLOCK violations must halt deployment.
    """

    constraint: str = Field(..., description="Which constraint was violated")
    severity: Severity = Field(..., description="Violation severity")
    message: str = Field(..., description="Human-readable violation description")
    expected: Any = Field(None, description="Expected value/condition")
    actual: Any = Field(None, description="Actual value found")
    rationale: str = Field("", description="Why this matters")

    def __str__(self) -> str:
        prefix = (
            "DEPLOYMENT BLOCKED:"
            if self.severity == Severity.BLOCK
            else f"[{self.severity.value.upper()}]"
        )
        return f"{prefix} {self.constraint}: {self.message}"

    def is_blocking(self) -> bool:
        """Check if this violation should block deployment."""
        return self.severity == Severity.BLOCK


class GateResult(BaseModel):
    """Result of a deployment gate check.

    This is the primary output for CI/CD integration.
    """

    contract_name: str
    contract_version: str
    contract_hash: str
    trace_id: str
    model: str
    task_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Gate decision
    passed: bool = Field(..., description="Whether deployment is allowed")
    blocked: bool = Field(False, description="Whether deployment is HARD BLOCKED")

    # Violation details
    violations: list[Violation] = Field(default_factory=list)
    block_count: int = 0
    fail_count: int = 0
    warn_count: int = 0

    # For CI/CD
    exit_code: int = Field(0, description="Process exit code (non-zero = blocked)")

    def __str__(self) -> str:
        if self.blocked:
            return (
                f"DEPLOYMENT BLOCKED: {self.contract_name} ({self.block_count} blocking violations)"
            )
        elif not self.passed:
            return f"GATE FAILED: {self.contract_name} ({self.fail_count} failures)"
        else:
            return f"GATE PASSED: {self.contract_name}"

    def to_ci_output(self) -> dict:
        """Output format for CI/CD systems."""
        return {
            "passed": self.passed,
            "blocked": self.blocked,
            "exit_code": self.exit_code,
            "contract": self.contract_name,
            "version": self.contract_version,
            "hash": self.contract_hash,
            "model": self.model,
            "trace_id": self.trace_id,
            "violations": [
                {
                    "severity": v.severity.value,
                    "constraint": v.constraint,
                    "message": v.message,
                }
                for v in self.violations
            ],
            "summary": {
                "block": self.block_count,
                "fail": self.fail_count,
                "warn": self.warn_count,
            },
        }

    def report(self, verbose: bool = True) -> str:
        """Generate human-readable policy check report (legacy gate CLI)."""
        lines = [
            "=" * 60,
            "Cogscope policy check",
            "=" * 60,
            "",
            f"Policy: {self.contract_name} v{self.contract_version}",
            f"Hash: {self.contract_hash}",
            f"Model: {self.model}",
            f"Trace: {self.trace_id}",
            "",
        ]

        if self.blocked:
            lines.extend(
                [
                    "STATUS: BLOCKED",
                    "",
                    f"Blocking violations: {self.block_count}",
                    f"Other failures: {self.fail_count}",
                    f"Warnings: {self.warn_count}",
                    "",
                ]
            )
        elif not self.passed:
            lines.extend(
                [
                    "STATUS: FAILED",
                    "",
                    f"Failures: {self.fail_count}",
                    f"Warnings: {self.warn_count}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "STATUS: PASSED",
                    "",
                    f"Warnings: {self.warn_count}",
                    "",
                ]
            )

        if self.violations and verbose:
            lines.append("VIOLATIONS:")
            lines.append("-" * 40)
            for v in self.violations:
                severity_label = (
                    "BLOCK" if v.severity == Severity.BLOCK else v.severity.value.upper()
                )
                lines.append(f"[{severity_label}] {v.constraint}")
                lines.append(f"  {v.message}")
                if v.expected:
                    lines.append(f"  Expected: {v.expected}")
                if v.actual:
                    lines.append(f"  Actual: {v.actual}")
                if v.rationale:
                    lines.append(f"  Why: {v.rationale}")
                lines.append("")

        lines.extend(
            [
                "=" * 60,
                f"EXIT CODE: {self.exit_code}",
                "=" * 60,
            ]
        )

        return "\n".join(lines)
