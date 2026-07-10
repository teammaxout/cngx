"""Execution-grounded verification for coding-agent output.

cngx verify runs the checks an agent claims it ran, then compares the real
result to what the agent said. The verdict is bound to actual command output,
not to the prose of the agent's message, so it cannot be gamed by writing
"all tests passed" without running anything.
"""

from __future__ import annotations

from cngx.verify.claims import Claim, extract_claim
from cngx.verify.parsers import TestResult, parse_output
from cngx.verify.runner import RunResult, run_command
from cngx.verify.verdict import Verdict, decide

__all__ = [
    "Claim",
    "extract_claim",
    "TestResult",
    "parse_output",
    "RunResult",
    "run_command",
    "Verdict",
    "decide",
]
