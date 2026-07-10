"""Parse real test-runner output into a normalized result.

The overall pass/fail verdict comes from the process exit code (authoritative).
Parsed counts are best-effort and used for the receipt and for catching a
claim that contradicts reality (e.g. agent said "12 passed", reality "9 passed").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TestResult:
    """Normalized result of a verification command or log."""

    __test__ = False  # not a pytest test class

    ok: bool
    framework: str
    passed: Optional[int] = None
    failed: Optional[int] = None
    errors: Optional[int] = None
    skipped: Optional[int] = None
    total: Optional[int] = None
    summary_line: Optional[str] = None

    @property
    def failing(self) -> int:
        """Failures plus errors, treating unknown as zero."""
        return (self.failed or 0) + (self.errors or 0)


def _first_int(match: Optional[re.Match[str]]) -> Optional[int]:
    return int(match.group(1)) if match else None


def _find_summary_line(text: str, keywords: tuple[str, ...]) -> Optional[str]:
    best: Optional[str] = None
    for line in text.splitlines():
        low = line.lower()
        if any(k in low for k in keywords):
            best = line.strip()
    return best


def _parse_pytest(text: str) -> Optional[TestResult]:
    # Matches "===== 9 passed, 3 failed, 1 skipped in 0.4s ====="
    if "passed" not in text and "failed" not in text and "error" not in text:
        return None
    passed = _first_int(re.search(r"(\d+)\s+passed", text))
    failed = _first_int(re.search(r"(\d+)\s+failed", text))
    errors = _first_int(re.search(r"(\d+)\s+errors?\b", text))
    skipped = _first_int(re.search(r"(\d+)\s+skipped", text))
    xfailed = _first_int(re.search(r"(\d+)\s+xfailed", text))
    if passed is None and failed is None and errors is None:
        return None
    summary = _find_summary_line(text, ("passed", "failed", "error"))
    total = None
    counts = [c for c in (passed, failed, errors, skipped, xfailed) if c is not None]
    if counts:
        total = sum(counts)
    ok = (failed or 0) == 0 and (errors or 0) == 0 and (passed or 0) >= 0
    return TestResult(
        ok=ok,
        framework="pytest",
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        total=total,
        summary_line=summary,
    )


def _parse_unittest(text: str) -> Optional[TestResult]:
    ran = re.search(r"Ran\s+(\d+)\s+tests?", text)
    if not ran:
        return None
    total = int(ran.group(1))
    failed = _first_int(re.search(r"failures=(\d+)", text))
    errors = _first_int(re.search(r"errors=(\d+)", text))
    skipped = _first_int(re.search(r"skipped=(\d+)", text))
    is_ok = bool(re.search(r"^OK\b", text, re.MULTILINE)) or "\nOK" in text
    is_fail = "FAILED" in text
    failed = failed or 0
    errors = errors or 0
    ok = is_ok and not is_fail and failed == 0 and errors == 0
    passed = max(total - failed - errors - (skipped or 0), 0)
    summary = _find_summary_line(text, ("ran ", "ok", "failed"))
    return TestResult(
        ok=ok,
        framework="unittest",
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        total=total,
        summary_line=summary,
    )


def _parse_jest(text: str) -> Optional[TestResult]:
    # "Tests:       3 failed, 9 passed, 12 total"
    line = re.search(r"Tests:\s+.*?(\d+\s+total)", text)
    if not line:
        return None
    passed = _first_int(re.search(r"(\d+)\s+passed", text))
    failed = _first_int(re.search(r"(\d+)\s+failed", text))
    skipped = _first_int(re.search(r"(\d+)\s+(?:skipped|todo)", text))
    total = _first_int(re.search(r"(\d+)\s+total", text))
    ok = (failed or 0) == 0
    return TestResult(
        ok=ok,
        framework="jest",
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total,
        summary_line=line.group(0).strip(),
    )


def _parse_go(text: str) -> Optional[TestResult]:
    if (
        "--- FAIL" not in text
        and "--- PASS" not in text
        and not re.search(r"^(ok|FAIL)\s", text, re.MULTILINE)
    ):
        return None
    passed = len(re.findall(r"--- PASS", text))
    failed = len(re.findall(r"--- FAIL", text))
    has_fail = bool(re.search(r"^FAIL\b", text, re.MULTILINE)) or failed > 0
    ok = not has_fail
    summary = _find_summary_line(text, ("ok  ", "fail", "pass"))
    return TestResult(
        ok=ok,
        framework="go",
        passed=passed or None,
        failed=failed or None,
        total=(passed + failed) or None,
        summary_line=summary,
    )


def _parse_cargo(text: str) -> Optional[TestResult]:
    m = re.search(r"test result:\s+(ok|FAILED)\.\s+(\d+)\s+passed;\s+(\d+)\s+failed", text)
    if not m:
        return None
    ok = m.group(1) == "ok"
    passed = int(m.group(2))
    failed = int(m.group(3))
    return TestResult(
        ok=ok and failed == 0,
        framework="cargo",
        passed=passed,
        failed=failed,
        total=passed + failed,
        summary_line=m.group(0).strip(),
    )


# Order matters: jest and cargo summaries also contain "N passed", so the
# generic pytest count parser must run last as a fallback.
_PARSERS = (_parse_jest, _parse_cargo, _parse_unittest, _parse_go, _parse_pytest)


def parse_output(text: str, exit_code: Optional[int] = None) -> TestResult:
    """Parse combined stdout+stderr into a normalized TestResult.

    If exit_code is provided (a real process run), it is authoritative for the
    overall ok verdict; parsed counts refine the receipt. If exit_code is None
    (a static log), ok is inferred from parsed counts and result markers.
    """
    text = text or ""
    parsed: Optional[TestResult] = None
    for parser in _PARSERS:
        try:
            result = parser(text)
        except Exception:
            result = None
        if result is not None:
            parsed = result
            break

    if parsed is None:
        # Generic: rely on exit code, or fall back to explicit markers in a log.
        if exit_code is not None:
            return TestResult(ok=exit_code == 0, framework="command")
        ok = _infer_ok_from_markers(text)
        return TestResult(ok=ok, framework="log")

    if exit_code is not None:
        # Process exit code is the source of truth; keep parsed counts.
        ok = exit_code == 0 and parsed.failing == 0
        return TestResult(
            ok=ok,
            framework=parsed.framework,
            passed=parsed.passed,
            failed=parsed.failed,
            errors=parsed.errors,
            skipped=parsed.skipped,
            total=parsed.total,
            summary_line=parsed.summary_line,
        )
    return parsed


_RESULT_MARKERS = (
    re.compile(r"\d+\s+passed", re.IGNORECASE),
    re.compile(r"\bAll tests passed\b", re.IGNORECASE),
    re.compile(r"\bBUILD SUCCESS\b", re.IGNORECASE),
    re.compile(r"exit code[=:\s]+0\b", re.IGNORECASE),
    re.compile(r"^OK\b", re.MULTILINE),
)
_FAILURE_MARKERS = (
    re.compile(r"\d+\s+failed", re.IGNORECASE),
    re.compile(r"\bFAILED\b"),
    re.compile(r"\bERROR\b"),
    re.compile(r"\bBUILD FAILURE\b", re.IGNORECASE),
    re.compile(r"exit code[=:\s]+(?!0\b)\d+", re.IGNORECASE),
)


def _infer_ok_from_markers(text: str) -> bool:
    has_pass = any(p.search(text) for p in _RESULT_MARKERS)
    has_fail = any(p.search(text) for p in _FAILURE_MARKERS)
    return has_pass and not has_fail
