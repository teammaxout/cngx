"""Extract what a coding agent claimed about its own verification.

We only look for strong, specific assertions of success. Precision matters more
than recall here: a false "the agent claimed success" would produce a wrong
verdict, so ambiguous words alone (like "done") are not treated as claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Strong assertions that the work is verified / merge-ready.
_SUCCESS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\ball tests? pass(?:ed|ing)?\b", re.I), "all tests pass"),
    (re.compile(r"\btests? (?:are )?pass(?:ed|ing)\b", re.I), "tests pass"),
    (re.compile(r"\ball (?:the )?tests? (?:are )?green\b", re.I), "all tests green"),
    (re.compile(r"\beverything pass(?:es|ed)\b", re.I), "everything passes"),
    (re.compile(r"\bpass(?:es|ed) all (?:the )?tests?\b", re.I), "passes all tests"),
    (re.compile(r"\bready to merge\b", re.I), "ready to merge"),
    (re.compile(r"\bsafe to merge\b", re.I), "safe to merge"),
    (re.compile(r"\bready for (?:review|merge)\b", re.I), "ready for review"),
    (re.compile(r"\bgood to merge\b", re.I), "good to merge"),
    (re.compile(r"\bLGTM\b"), "LGTM"),
    (re.compile(r"\bship it\b", re.I), "ship it"),
    (re.compile(r"\bthe (?:fix|change|patch) works\b", re.I), "the fix works"),
    (re.compile(r"\bworks as expected\b", re.I), "works as expected"),
    (re.compile(r"\bno (?:test )?failures\b", re.I), "no failures"),
    (re.compile(r"\bno errors\b", re.I), "no errors"),
    (
        re.compile(r"\bsuccessfully (?:fixed|resolved|implemented|verified)\b", re.I),
        "successfully done",
    ),
    (
        re.compile(r"\bverified (?:the )?(?:fix|change|it works|behaviou?r)\b", re.I),
        "verified the fix",
    ),
    (re.compile(r"\bconfirmed (?:the )?tests? pass\b", re.I), "confirmed tests pass"),
    (re.compile(r"\bexit code[=:\s]+0\b", re.I), "exit code 0"),
)

_PASSED_COUNT = re.compile(r"(\d+)\s+(?:tests?\s+)?passed", re.I)
_FAILED_COUNT = re.compile(r"(\d+)\s+(?:tests?\s+)?failed", re.I)
_NO_FAIL = re.compile(r"\b(?:no (?:tests? )?fail(?:ures|ed)?|0 failed|nothing fail)", re.I)


@dataclass(frozen=True)
class Claim:
    """What the agent asserted about verification, parsed from its message."""

    claims_success: bool = False
    claimed_passed: Optional[int] = None
    claimed_failed: Optional[int] = None
    claimed_no_failures: bool = False
    markers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_claim(self) -> bool:
        return self.claims_success or self.claimed_passed is not None


def extract_claim(text: Optional[str]) -> Claim:
    body = (text or "").strip()
    if not body:
        return Claim()

    markers: list[str] = []
    for pattern, label in _SUCCESS_PATTERNS:
        if pattern.search(body):
            markers.append(label)

    passed_match = _PASSED_COUNT.search(body)
    failed_match = _FAILED_COUNT.search(body)
    claimed_passed = int(passed_match.group(1)) if passed_match else None
    claimed_failed = int(failed_match.group(1)) if failed_match else None
    no_failures = bool(_NO_FAIL.search(body))

    # A specific passing count with no admitted failures is itself a success claim.
    claims_success = bool(markers)
    if claimed_passed is not None and (claimed_failed in (None, 0)):
        claims_success = True
        if not markers:
            markers.append(f"{claimed_passed} passed")

    return Claim(
        claims_success=claims_success,
        claimed_passed=claimed_passed,
        claimed_failed=claimed_failed,
        claimed_no_failures=no_failures,
        markers=tuple(dict.fromkeys(markers)),
    )
