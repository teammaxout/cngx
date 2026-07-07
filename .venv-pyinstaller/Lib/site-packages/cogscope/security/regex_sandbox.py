"""Safe regex execution with ReDoS protection.

Contracts accept user-supplied regex patterns. A malicious or poorly-written
pattern (e.g., (a+)+b) can trigger catastrophic backtracking against large
LLM outputs (100 KB+), hanging the enforcement pipeline.

This module provides:
1. Pattern complexity validation on contract load
2. Execution timeout via threading (cross-platform)
3. Input length capping for regex operations
"""

import re
import threading
from typing import Optional, Pattern

from cogscope.core.exceptions import ContractError


class RegexTimeoutError(Exception):
    """Raised when regex execution exceeds the time limit."""

    def __init__(self, pattern: str, timeout_seconds: float):
        self.pattern = pattern
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Regex execution timed out after {timeout_seconds}s. "
            f"Pattern may be vulnerable to catastrophic backtracking: {pattern[:80]}..."
        )


class RegexComplexityError(Exception):
    """Raised when a regex pattern is considered too complex/dangerous."""

    def __init__(self, pattern: str, reason: str):
        self.pattern = pattern
        self.reason = reason
        super().__init__(f"Regex pattern rejected (complexity): {reason}. Pattern: {pattern[:80]}")


# ---- Complexity heuristics ----

# Patterns known to cause catastrophic backtracking
_DANGEROUS_PATTERNS = [
    re.compile(r"\([^)]*[+*][^)]*\)[+*]"),  # (a+)+ or (a*)*, nested quantifiers
    re.compile(r"\([^)]*\|[^)]*\)[+*]{"),  # (a|b){n,m} with overlap
    re.compile(r"\.{2,}[+*]"),  # ..+ or ..*
]

# Maximum allowed pattern length
MAX_PATTERN_LENGTH = 1000

# Maximum input length for regex matching (characters)
MAX_INPUT_LENGTH = 500_000  # 500KB, generous for LLM output

# Default execution timeout
DEFAULT_TIMEOUT_SECONDS = 2.0


def validate_pattern_complexity(pattern: str) -> None:
    """Validate that a regex pattern is not dangerous.

    Raises RegexComplexityError if the pattern fails safety checks.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexComplexityError(
            pattern, f"Pattern length {len(pattern)} exceeds maximum {MAX_PATTERN_LENGTH}"
        )

    for dangerous in _DANGEROUS_PATTERNS:
        if dangerous.search(pattern):
            raise RegexComplexityError(
                pattern,
                "Pattern contains nested quantifiers or other backtracking-prone constructs",
            )


def safe_regex_compile(
    pattern: str,
    flags: int = 0,
    validate_complexity: bool = True,
) -> Pattern:
    """Compile a regex pattern with safety checks.

    Args:
        pattern: The regex pattern string
        flags: re.IGNORECASE etc.
        validate_complexity: Whether to check for dangerous patterns

    Returns:
        Compiled regex pattern

    Raises:
        RegexComplexityError: If pattern fails safety checks
        re.error: If pattern is syntactically invalid
    """
    if validate_complexity:
        validate_pattern_complexity(pattern)

    try:
        return re.compile(pattern, flags)
    except re.error as e:
        raise ContractError(f"Invalid regex pattern '{pattern[:80]}': {e}") from e


def safe_regex_search(
    pattern: Pattern,
    text: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_length: int = MAX_INPUT_LENGTH,
) -> Optional[re.Match]:
    """Execute a regex search with timeout and input length protection.

    Uses a background thread to enforce timeout on regex execution.
    This is a cross-platform approach (works on Windows, Linux, macOS).

    Args:
        pattern: Compiled regex pattern
        text: Input text to search
        timeout_seconds: Maximum execution time
        max_input_length: Maximum input text length

    Returns:
        re.Match or None

    Raises:
        RegexTimeoutError: If execution exceeds timeout
    """
    # Cap input length
    if len(text) > max_input_length:
        text = text[:max_input_length]

    result: list = []
    error: list = []

    def _search():
        try:
            match = pattern.search(text)
            result.append(match)
        except Exception as e:
            error.append(e)

    thread = threading.Thread(target=_search, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Thread is still running, regex is backtracking
        raise RegexTimeoutError(pattern.pattern, timeout_seconds)

    if error:
        raise error[0]

    return result[0] if result else None


def safe_regex_findall(
    pattern: Pattern,
    text: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_length: int = MAX_INPUT_LENGTH,
) -> list[str]:
    """Execute a regex findall with timeout protection.

    Args:
        pattern: Compiled regex pattern
        text: Input text to search
        timeout_seconds: Maximum execution time
        max_input_length: Maximum input text length

    Returns:
        List of matches

    Raises:
        RegexTimeoutError: If execution exceeds timeout
    """
    if len(text) > max_input_length:
        text = text[:max_input_length]

    result: list = []
    error: list = []

    def _findall():
        try:
            matches = pattern.findall(text)
            result.append(matches)
        except Exception as e:
            error.append(e)

    thread = threading.Thread(target=_findall, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise RegexTimeoutError(pattern.pattern, timeout_seconds)

    if error:
        raise error[0]

    return result[0] if result else []
