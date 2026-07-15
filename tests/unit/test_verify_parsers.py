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


def test_vitest_all_passed_with_skips():
    text = (
        "\x1b[32m Test Files  2 passed (2)\x1b[39m\n"
        "\x1b[32m      Tests  12 passed | 3 skipped (15)\x1b[39m"
    )
    r = parse_output(text, exit_code=0)
    assert r.framework == "vitest"
    assert r.passed == 12
    assert r.failed is None
    assert r.skipped == 3
    assert r.total == 15
    assert r.ok is True


def test_vitest_with_failures():
    text = " Test Files  1 failed | 2 passed (3)\n      Tests  1 failed | 8 passed (9)"
    r = parse_output(text, exit_code=1)
    assert r.framework == "vitest"
    assert r.passed == 8
    assert r.failed == 1
    assert r.total == 9
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


def test_rspec_all_passed():
    text = "Finished in 0.5 seconds (files took 0.1 seconds to load)\n5 examples, 0 failures"
    r = parse_output(text, exit_code=0)
    assert r.framework == "rspec"
    assert r.passed == 5
    assert r.failing == 0
    assert r.ok is True


def test_rspec_with_failures():
    text = "6 examples, 2 failures, 1 pending"
    r = parse_output(text, exit_code=1)
    assert r.framework == "rspec"
    assert r.failed == 2
    assert r.skipped == 1
    assert r.passed == 3
    assert r.ok is False


def test_phpunit_ok():
    text = "OK (24 tests, 42 assertions)"
    r = parse_output(text, exit_code=0)
    assert r.framework == "phpunit"
    assert r.passed == 24
    assert r.failing == 0
    assert r.ok is True


def test_phpunit_with_failures_and_errors():
    text = "Tests: 24, Assertions: 42, Failures: 3, Errors: 1"
    r = parse_output(text, exit_code=1)
    assert r.framework == "phpunit"
    assert r.failed == 3
    assert r.errors == 1
    assert r.failing == 4
    assert r.ok is False


def test_dotnet_passed():
    text = "Passed!  - Failed: 0, Passed: 10, Skipped: 0, Total: 10 - MyTests.dll (net8.0)"
    r = parse_output(text, exit_code=0)
    assert r.framework == "dotnet"
    assert r.passed == 10
    assert r.total == 10
    assert r.ok is True


def test_dotnet_failed():
    text = "Failed!  - Failed: 2, Passed: 8, Skipped: 0, Total: 10 - MyTests.dll (net8.0)"
    r = parse_output(text, exit_code=1)
    assert r.framework == "dotnet"
    assert r.failed == 2
    assert r.passed == 8
    assert r.ok is False


def test_mocha_all_passing():
    text = "  12 passing (34ms)"
    r = parse_output(text, exit_code=0)
    assert r.framework == "mocha"
    assert r.passed == 12
    assert r.failing == 0
    assert r.ok is True


def test_mocha_with_failing():
    text = "  10 passing (2s)\n  2 failing"
    r = parse_output(text, exit_code=1)
    assert r.framework == "mocha"
    assert r.passed == 10
    assert r.failed == 2
    assert r.ok is False


def test_surefire_all_passed():
    text = "Tests run: 10, Failures: 0, Errors: 0, Skipped: 0"
    r = parse_output(text, exit_code=0)
    assert r.framework == "surefire"
    assert r.passed == 10
    assert r.failing == 0
    assert r.ok is True


def test_surefire_with_failures_and_errors():
    text = "Tests run: 10, Failures: 2, Errors: 1, Skipped: 0"
    r = parse_output(text, exit_code=1)
    assert r.framework == "surefire"
    assert r.failed == 2
    assert r.errors == 1
    assert r.failing == 3
    assert r.ok is False


def test_mocha_does_not_match_prose():
    # "N passing" in arbitrary prose is not a mocha summary; it must not be parsed as one.
    text = "We have 3 passing cars in the lot"
    r = parse_output(text, exit_code=0)
    assert r.framework != "mocha"


def test_mocha_does_not_hijack_pytest_with_passing_in_prose():
    # A pytest log that merely mentions "passing" alongside its own "N passed" summary must still
    # resolve to pytest with the correct count, not be captured by the mocha parser.
    text = "collected 5 items\ntest session: 12 passing checks configured\n5 passed in 0.3s"
    r = parse_output(text, exit_code=0)
    assert r.framework == "pytest"
    assert r.passed == 5
