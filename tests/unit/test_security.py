"""Unit tests for the regex sandbox security module.

Tests ReDoS protection, pattern complexity validation,
execution timeouts, and input length capping.
"""

import re

import pytest

from cogscope.security.regex_sandbox import (
    MAX_INPUT_LENGTH,
    MAX_PATTERN_LENGTH,
    RegexComplexityError,
    RegexTimeoutError,
    safe_regex_compile,
    safe_regex_findall,
    safe_regex_search,
    validate_pattern_complexity,
)


class TestPatternComplexity:
    """Tests for regex pattern safety validation."""

    def test_safe_pattern_passes(self):
        """Normal patterns should pass validation."""
        validate_pattern_complexity(r"\b\d+\.\d+\b")
        validate_pattern_complexity(r"hello|world")
        validate_pattern_complexity(r"step\s*\d+")

    def test_nested_quantifiers_rejected(self):
        """(a+)+ patterns should be rejected — classic ReDoS."""
        with pytest.raises(RegexComplexityError, match="nested quantifiers"):
            validate_pattern_complexity(r"(a+)+")

    def test_nested_star_rejected(self):
        with pytest.raises(RegexComplexityError, match="nested quantifiers"):
            validate_pattern_complexity(r"(a*)*")

    def test_pattern_too_long(self):
        """Patterns exceeding MAX_PATTERN_LENGTH should be rejected."""
        long_pattern = "a" * (MAX_PATTERN_LENGTH + 1)
        with pytest.raises(RegexComplexityError, match="exceeds maximum"):
            validate_pattern_complexity(long_pattern)

    def test_max_length_boundary(self):
        """Pattern exactly at MAX_PATTERN_LENGTH should pass."""
        pattern = "a" * MAX_PATTERN_LENGTH
        validate_pattern_complexity(pattern)  # Should not raise


class TestSafeCompile:
    """Tests for safe_regex_compile."""

    def test_compile_valid_pattern(self):
        pat = safe_regex_compile(r"\bhello\b", flags=re.IGNORECASE)
        assert pat.search("Hello world") is not None

    def test_compile_invalid_syntax(self):
        from cogscope.core.exceptions import ContractError

        with pytest.raises(ContractError, match="Invalid regex"):
            safe_regex_compile(r"(unclosed")

    def test_compile_dangerous_pattern(self):
        with pytest.raises(RegexComplexityError):
            safe_regex_compile(r"(a+)+b")

    def test_compile_skip_validation(self):
        """Should compile dangerous patterns when validation is disabled."""
        pat = safe_regex_compile(r"(a+)+b", validate_complexity=False)
        assert pat is not None


class TestSafeSearch:
    """Tests for safe_regex_search with timeout."""

    def test_normal_search(self):
        pat = safe_regex_compile(r"\d+")
        match = safe_regex_search(pat, "abc 123 def")
        assert match is not None
        assert match.group() == "123"

    def test_search_no_match(self):
        pat = safe_regex_compile(r"xyz")
        match = safe_regex_search(pat, "abc 123 def")
        assert match is None

    def test_input_capped_at_max_length(self):
        """Long inputs should be truncated, not rejected."""
        pat = safe_regex_compile(r"end_marker")
        # Place marker beyond the cap — it should NOT be found
        text = "a" * (MAX_INPUT_LENGTH + 100) + "end_marker"
        match = safe_regex_search(pat, text)
        assert match is None

    def test_input_within_limit(self):
        pat = safe_regex_compile(r"found")
        text = "a" * 1000 + "found" + "b" * 1000
        match = safe_regex_search(pat, text)
        assert match is not None


class TestSafeFindall:
    """Tests for safe_regex_findall."""

    def test_findall_multiple_matches(self):
        pat = safe_regex_compile(r"\d+")
        matches = safe_regex_findall(pat, "a1 b22 c333")
        assert matches == ["1", "22", "333"]

    def test_findall_no_matches(self):
        pat = safe_regex_compile(r"xyz")
        matches = safe_regex_findall(pat, "abc def ghi")
        assert matches == []

    def test_findall_input_capped(self):
        pat = safe_regex_compile(r"tail")
        text = "x" * (MAX_INPUT_LENGTH + 100) + "tail"
        matches = safe_regex_findall(pat, text)
        assert len(matches) == 0  # Truncated before "tail"


class TestErrorTypes:
    def test_regex_timeout_error_message(self):
        err = RegexTimeoutError("(a+)+b", 2.0)
        assert "2.0s" in str(err)
        assert "(a+)+b" in str(err)

    def test_regex_complexity_error_message(self):
        err = RegexComplexityError("(a+)+", "nested quantifiers")
        assert "nested quantifiers" in str(err)
