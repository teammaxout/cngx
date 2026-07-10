"""Cross-check agent claims against real command evidence (pytest logs, etc.)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Concrete result shapes, not narrative claims like "I ran pytest".
_RESULT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+\s+passed", re.IGNORECASE),
    re.compile(r"\d+\s+tests?\s+passed", re.IGNORECASE),
    re.compile(r"\bPASSED\b"),
    re.compile(r"All tests passed", re.IGNORECASE),
    re.compile(r"exit code[=:\s]+0\b", re.IGNORECASE),
    re.compile(r"====+.*passed.*====+", re.IGNORECASE),
)

_FAILURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+\s+failed", re.IGNORECASE),
    re.compile(r"\bFAILED\b"),
    re.compile(r"exit code[=:\s]+(?!0\b)\d+", re.IGNORECASE),
)


@dataclass(frozen=True)
class EvidenceCheck:
    """Result of validating a CI/test evidence file."""

    ok: bool
    reasons: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def first_result_snippet(text: str) -> str | None:
    """Return the first log line that matches a concrete result pattern.

    Used to inject real CI evidence into offline agent output before the
    policy check, so a solid writeup that omitted pasting pytest output can
    still satisfy required result patterns when CI supplies a real log.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped and any(p.search(stripped) for p in _RESULT_PATTERNS):
            return stripped
    body = (text or "").strip()
    if not body:
        return None
    for pattern in _RESULT_PATTERNS:
        match = pattern.search(body)
        if match:
            return match.group(0)
    return None


def check_evidence_text(text: str) -> EvidenceCheck:
    """Require concrete test-result evidence in a log or artifact file.

    This is still not cryptographic proof of execution, but it raises the bar
    above agent narrative alone: the evidence file must look like real tool output.
    """
    body = (text or "").strip()
    if not body:
        return EvidenceCheck(False, ("evidence file is empty",))

    reasons: list[str] = []
    if any(p.search(body) for p in _FAILURE_PATTERNS) and not any(
        p.search(body) for p in _RESULT_PATTERNS
    ):
        reasons.append("evidence shows test failures without a passing result line")

    if not any(p.search(body) for p in _RESULT_PATTERNS):
        reasons.append(
            "evidence lacks a concrete result line "
            "(expected e.g. '12 passed', 'PASSED', or 'exit code 0')"
        )

    if reasons:
        return EvidenceCheck(False, tuple(reasons))
    return EvidenceCheck(True, ())
