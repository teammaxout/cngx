"""CI/CD policy enforcement with hard exit codes."""

from cogscope.enforcement.gate import EnforcementConfig, EnforcementGate, EnforcementResult
from cogscope.enforcement.github_action import GitHubActionGenerator

__all__ = [
    "EnforcementGate",
    "EnforcementConfig",
    "EnforcementResult",
    "GitHubActionGenerator",
]
