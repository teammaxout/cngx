"""
BRUTAL TEST: Provider Infrastructure & Security

Tests rate limiting, retry logic, circuit breaker, and security features.
"""

import threading
import time

import pytest

from cogscope.core.models import TokenUsage
from cogscope.providers.base import TokenAccountant
from cogscope.providers.rate_limiter import RateLimiter, TokenBucket
from cogscope.providers.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    RetryConfig,
    compute_delay,
    retry_with_backoff,
)
from cogscope.security.regex_sandbox import (
    RegexComplexityError,
    RegexTimeoutError,
    safe_regex_compile,
    safe_regex_findall,
    safe_regex_search,
)


class TestTokenBucket:
    """Test token bucket rate limiting."""

    def test_initial_capacity(self):
        """Bucket should start with full capacity."""
        bucket = TokenBucket(rate=1.0, capacity=10)
        assert bucket.consume(10), "Should be able to consume full capacity"

    def test_overconsume_rejected(self):
        """Consuming more than capacity should fail."""
        bucket = TokenBucket(rate=1.0, capacity=5)
        assert not bucket.consume(6), "Should not consume more than capacity"

    def test_refill_after_wait(self):
        """Bucket should refill over time."""
        bucket = TokenBucket(rate=100.0, capacity=5)  # 100 tokens/sec
        bucket.consume(5)  # Empty it
        time.sleep(0.1)  # Wait for refill (~10 tokens at 100/sec)
        assert bucket.consume(1), "Should have refilled after waiting"

    def test_thread_safety(self):
        """Multiple threads consuming from same bucket should not corrupt state."""
        bucket = TokenBucket(rate=0.0, capacity=100)  # No refill
        results = []

        def consume():
            success = bucket.consume(1)
            results.append(success)

        threads = [threading.Thread(target=consume) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 100 should succeed (capacity=100, each takes 1)
        assert sum(results) == 100

    def test_available_property(self):
        """Available property should reflect remaining capacity."""
        bucket = TokenBucket(rate=0.0, capacity=10)
        assert bucket.available == 10.0
        bucket.consume(3)
        assert bucket.available == 7.0


class TestCircuitBreaker:
    """Test circuit breaker pattern."""

    def test_starts_closed(self):
        """New circuit breaker should be closed."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        """Should open after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_after_recovery(self):
        """Should transition to HALF_OPEN after recovery timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.05)
        cb = CircuitBreaker(config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.2)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success(self):
        """Should close after success in HALF_OPEN state."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.05,
            success_threshold=1,
        )
        cb = CircuitBreaker(config)
        cb.record_failure()
        time.sleep(0.2)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_half_open_failure(self):
        """Failure in HALF_OPEN should re-open the circuit."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.05)
        cb = CircuitBreaker(config)
        cb.record_failure()
        time.sleep(0.2)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_allows_request_when_closed(self):
        """Closed circuit should allow requests."""
        cb = CircuitBreaker()
        assert cb.allow_request() is True

    def test_blocks_request_when_open(self):
        """Open circuit should block requests."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=10)
        cb = CircuitBreaker(config)
        cb.record_failure()
        assert cb.allow_request() is False

    def test_reset(self):
        """Reset should return to closed state."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker(config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestRetryLogic:
    """Test retry with backoff."""

    def test_compute_delay_increases(self):
        """Delay should increase with attempt number."""
        config = RetryConfig(base_delay=1.0, max_delay=60.0, exponential_base=2.0, jitter=False)
        d1 = compute_delay(1, config)
        d2 = compute_delay(2, config)
        d3 = compute_delay(3, config)
        assert d1 < d2 < d3, f"Delays should increase: {d1}, {d2}, {d3}"

    def test_delay_capped_at_max(self):
        """Delay should never exceed max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=10.0, exponential_base=2.0, jitter=False)
        delay = compute_delay(100, config)
        assert delay <= 10.0, f"Delay should be capped at 10.0, got {delay}"

    def test_retry_succeeds_eventually(self):
        """Function that succeeds on 3rd attempt should work with retry."""
        attempts = [0]

        @retry_with_backoff(config=RetryConfig(max_retries=5, base_delay=0.01))
        def flaky_function():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Transient failure")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert attempts[0] == 3


class TestTokenAccountant:
    """Test token usage and cost tracking."""

    def setup_method(self):
        self.accountant = TokenAccountant()

    def test_record_usage(self):
        """Should record token usage."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        self.accountant.record(model="gpt-4o", usage=usage)
        report = self.accountant.get_report()
        assert report["total_tokens"] >= 150

    def test_cost_estimation(self):
        """Should estimate cost for known models."""
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        self.accountant.record(model="gpt-4o", usage=usage)
        report = self.accountant.get_report()
        assert report["total_cost_usd"] > 0, "Cost should be positive for GPT-4o"

    def test_thread_safety(self):
        """Concurrent recording should not lose data."""
        accountant = TokenAccountant()

        def record():
            usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
            accountant.record(model="test", usage=usage)

        threads = [threading.Thread(target=record) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        report = accountant.get_report()
        assert report["per_model"]["test"]["prompt_tokens"] == 500  # 50 * 10
        assert report["per_model"]["test"]["completion_tokens"] == 250  # 50 * 5

    def test_reset(self):
        """Reset should clear all data."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        self.accountant.record(model="gpt-4o", usage=usage)
        self.accountant.reset()
        report = self.accountant.get_report()
        assert report["total_tokens"] == 0


class TestRegexSandbox:
    """Test ReDoS protection."""

    def test_normal_regex_works(self):
        """Normal regex should compile and search fine."""
        pattern = safe_regex_compile(r"\btest\b")
        result = safe_regex_search(pattern, "this is a test string")
        assert result is not None

    def test_redos_pattern_blocked(self):
        """Known ReDoS patterns should be blocked."""
        with pytest.raises((RegexComplexityError, RegexTimeoutError, Exception)):
            # This is a classic ReDoS pattern
            safe_regex_compile(r"(a+)+b")

    def test_long_input_capped(self):
        """Very long input should be handled safely."""
        pattern = safe_regex_compile(r"test")
        # Large input should not hang
        safe_regex_search(pattern, "a" * 100000)
        # Should complete without hanging

    def test_findall_works(self):
        """safe_regex_findall should work like re.findall."""
        pattern = safe_regex_compile(r"\d+")
        results = safe_regex_findall(pattern, "abc 123 def 456")
        assert "123" in results
        assert "456" in results

    def test_invalid_regex_blocked(self):
        """Invalid regex syntax should raise clear error."""
        with pytest.raises(Exception):
            safe_regex_compile(r"[invalid")
