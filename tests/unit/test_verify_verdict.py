"""Tests for the claim-versus-reality verdict logic."""

from cngx.verify.claims import extract_claim
from cngx.verify.parsers import TestResult
from cngx.verify.verdict import decide


def _passed(n=3):
    return TestResult(ok=True, framework="pytest", passed=n, failed=0, summary_line=f"{n} passed")


def _failed(passed=1, failed=2):
    return TestResult(
        ok=False,
        framework="pytest",
        passed=passed,
        failed=failed,
        summary_line=f"{passed} passed, {failed} failed",
    )


def test_lie_is_blocked():
    v = decide(_failed(), extract_claim("all tests pass, ready to merge"))
    assert v.blocked
    assert v.exit_code == 1
    assert "claimed the work is done" in v.headline.lower()


def test_true_claim_verified():
    v = decide(_passed(3), extract_claim("all tests pass, 3 passed"))
    assert v.verified
    assert v.exit_code == 0


def test_failure_without_claim_still_blocked():
    v = decide(_failed(), extract_claim("here is a patch"))
    assert v.blocked
    assert "verification failed" in v.headline.lower()


def test_count_mismatch_blocked():
    v = decide(_passed(3), extract_claim("Done. 12 passed."))
    assert v.blocked
    assert "count" in v.headline.lower()


def test_count_match_verified():
    v = decide(_passed(12), extract_claim("Done. 12 passed."))
    assert v.verified


def test_require_claim_blocks_silent_pass():
    v = decide(_passed(3), extract_claim("patch attached"), require_claim=True)
    assert v.blocked
    assert "never claimed" in v.headline.lower()


def test_pass_without_claim_ok_by_default():
    v = decide(_passed(3), extract_claim("patch attached"))
    assert v.verified


def test_timeout_blocks():
    v = decide(_passed(3), extract_claim("all tests pass"), timed_out=True, timeout=5.0)
    assert v.blocked
    assert "did not finish" in v.headline.lower()
