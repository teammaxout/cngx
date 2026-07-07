"""Behavior Contracts - behavioral contract enforcement.

This package provides machine-readable contracts that define
HARD CONSTRAINTS on AI reasoning behavior.

BLOCK-level violations prevent deployment.
"""

from cogscope.contracts.schema import (
    BehaviorContract,
    DepthConstraint,
    DomainIntent,
    ForbiddenPattern,
    GateResult,
    OutputConstraint,
    RequiredPattern,
    Severity,
    StepsConstraint,
    ToolConstraint,
    UncertaintyConstraint,
    VerificationConstraint,
    Violation,
)
from cogscope.contracts.validator import (
    ContractValidator,
    DeploymentGate,
    validate_contract,
)

__all__ = [
    # Schema
    "BehaviorContract",
    "Violation",
    "GateResult",
    "Severity",
    "DomainIntent",
    # Constraints
    "DepthConstraint",
    "StepsConstraint",
    "VerificationConstraint",
    "ToolConstraint",
    "UncertaintyConstraint",
    "OutputConstraint",
    "ForbiddenPattern",
    "RequiredPattern",
    # Validation
    "ContractValidator",
    "DeploymentGate",
    "validate_contract",
]
