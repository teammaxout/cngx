"""Bind an agent's claim to real execution and decide a verdict."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cngx.verify.claims import Claim
from cngx.verify.parsers import TestResult

VERIFIED = "verified"
BLOCKED = "blocked"
ERROR = "error"


@dataclass
class Verdict:
    """Outcome of comparing a claim to real command results."""

    status: str
    exit_code: int
    headline: str
    reasons: list[str] = field(default_factory=list)
    receipt: Optional[str] = None

    @property
    def blocked(self) -> bool:
        return self.status == BLOCKED

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "headline": self.headline,
            "reasons": self.reasons,
            "receipt": self.receipt,
        }


def _result_summary(result: TestResult) -> str:
    if result.summary_line:
        return result.summary_line
    bits = []
    if result.passed is not None:
        bits.append(f"{result.passed} passed")
    if result.failing:
        if result.failed:
            bits.append(f"{result.failed} failed")
        if result.errors:
            bits.append(f"{result.errors} errors")
    if bits:
        return ", ".join(bits)
    return "passed" if result.ok else "failed"


def decide(
    result: TestResult,
    claim: Claim,
    *,
    timed_out: bool = False,
    timeout: float = 0.0,
    require_claim: bool = False,
    command_label: Optional[str] = None,
) -> Verdict:
    """Compute the verdict from real results and the parsed claim."""
    label = command_label or result.framework
    receipt = _result_summary(result)

    if timed_out:
        return Verdict(
            status=BLOCKED,
            exit_code=1,
            headline="Verification did not finish.",
            reasons=[f"{label} timed out after {timeout:.0f}s before reporting a result."],
            receipt=receipt,
        )

    # Reality failed: the work does not actually pass.
    if not result.ok:
        reasons: list[str] = []
        if claim.claims_success:
            headline = "Agent claimed the work is done, but verification failed."
            if claim.markers:
                reasons.append("Agent said: " + ", ".join(f'"{m}"' for m in claim.markers))
        else:
            headline = "Verification failed."
        reasons.append(f"Real result: {receipt}")
        return Verdict(
            status=BLOCKED, exit_code=1, headline=headline, reasons=reasons, receipt=receipt
        )

    # Reality passed: check the claim does not contradict the numbers.
    if (
        claim.claimed_passed is not None
        and result.passed is not None
        and claim.claimed_passed != result.passed
    ):
        return Verdict(
            status=BLOCKED,
            exit_code=1,
            headline="Agent's test count does not match reality.",
            reasons=[
                f"Agent claimed {claim.claimed_passed} passed.",
                f"Real result: {receipt}",
            ],
            receipt=receipt,
        )

    if require_claim and not claim.claims_success:
        return Verdict(
            status=BLOCKED,
            exit_code=1,
            headline="Verification passed, but the agent never claimed to verify.",
            reasons=[
                "Policy requires an explicit verification claim in the agent output.",
                f"Real result: {receipt}",
            ],
            receipt=receipt,
        )

    if claim.has_claim:
        headline = "Verified. The agent's claim matches real execution."
    else:
        headline = "Verified."
    return Verdict(status=VERIFIED, exit_code=0, headline=headline, receipt=receipt)
