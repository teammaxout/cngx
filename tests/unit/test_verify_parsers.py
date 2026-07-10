"""Tests for normalized test-output parsing."""

from cngx.verify.parsers import parse_output


def test_pytest_all_passed():
    text = "=========== 12 passed in 0.43s ==========="
    r = parse_output(text, exit_code=0)
    assert r.ok is True
    assert r.framework == "pytest"
    assert r.passed == 12
    assert r.failing == 0


def test_pytest_with_failures():
    text = "=========== 9 passed, 3 failed in 1.2s ==========="
    r = parse_output(text, exit_code=1)
    assert r.ok is False
    assert r.passed == 9
    assert r.failed == 3
    assert r.failing == 3


def test_pytest_exit_code_authoritative_over_counts():
    # Even if the log shows passes, a nonzero exit code means not ok.
    text = "5 passed"
    r = parse_output(text, exit_code=2)
    assert r.ok is False


def test_pytest_errors_counted():
    text = "1 passed, 2 errors in 0.1s"
    r = parse_output(text, exit_code=1)
    assert r.errors == 2
    assert r.failing == 2
    assert r.ok is False


def test_unittest_ok():
    text = "Ran 3 tests in 0.01s\n\nOK"
    r = parse_output(text, exit_code=0)
    assert r.framework == "unittest"
    assert r.total == 3
    assert r.ok is True


def test_unittest_failed():
    text = "Ran 3 tests in 0.01s\n\nFAILED (failures=2)"
    r = parse_output(text, exit_code=1)
    assert r.framework == "unittest"
    assert r.failed == 2
    assert r.ok is False


def test_jest_summary():
    text = "Tests:       3 failed, 9 passed, 12 total"
    r = parse_output(text, exit_code=1)
    assert r.framework == "jest"
    assert r.passed == 9
    assert r.failed == 3
    assert r.total == 12
    assert r.ok is False


def test_cargo_ok():
    text = "test result: ok. 12 passed; 0 failed; 0 ignored"
    r = parse_output(text, exit_code=0)
    assert r.framework == "cargo"
    assert r.passed == 12
    assert r.ok is True


def test_cargo_failed():
    text = "test result: FAILED. 9 passed; 3 failed; 0 ignored"
    r = parse_output(text, exit_code=101)
    assert r.framework == "cargo"
    assert r.failed == 3
    assert r.ok is False


def test_go_fail():
    text = "--- FAIL: TestPaginate (0.00s)\nFAIL\nexit status 1"
    r = parse_output(text, exit_code=1)
    assert r.framework == "go"
    assert r.ok is False


def test_generic_uses_exit_code():
    r_ok = parse_output("built fine", exit_code=0)
    assert r_ok.framework == "command"
    assert r_ok.ok is True
    r_bad = parse_output("nope", exit_code=1)
    assert r_bad.ok is False


def test_log_without_exit_code_infers_from_markers():
    ok = parse_output("Everything green\n5 passed", exit_code=None)
    assert ok.ok is True
    bad = parse_output("2 failed, 1 passed", exit_code=None)
    assert bad.ok is False


def test_empty_log_not_ok():
    r = parse_output("", exit_code=None)
    assert r.ok is False
