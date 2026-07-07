"""Tests for cogscope.providers module."""

import time
from unittest.mock import patch

import pytest


class TestRetryConfig:
    def test_defaults(self):
        from cogscope.providers.retry import RetryConfig

        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert 429 in config.retryable_status_codes

    def test_custom(self):
        from cogscope.providers.retry import RetryConfig

        config = RetryConfig(max_retries=5, base_delay=0.5)
        assert config.max_retries == 5
        assert config.base_delay == 0.5


class TestCircuitBreaker:
    def test_initial_state(self):
        from cogscope.providers.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState

        cb = CircuitBreaker(CircuitBreakerConfig())
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_failures(self):
        from cogscope.providers.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState

        config = CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        cb = CircuitBreaker(config)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_after_recovery(self):
        from cogscope.providers.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState

        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.05)
        cb = CircuitBreaker(config)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success(self):
        from cogscope.providers.retry import CircuitBreaker, CircuitBreakerConfig, CircuitState

        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0.01, success_threshold=1
        )
        cb = CircuitBreaker(config)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


class TestComputeDelay:
    def test_exponential_backoff(self):
        from cogscope.providers.retry import RetryConfig, compute_delay

        config = RetryConfig(base_delay=1.0, jitter=False)
        d0 = compute_delay(0, config)
        d1 = compute_delay(1, config)
        d2 = compute_delay(2, config)
        assert d0 == 1.0
        assert d1 == 2.0
        assert d2 == 4.0

    def test_max_delay_cap(self):
        from cogscope.providers.retry import RetryConfig, compute_delay

        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)
        d = compute_delay(10, config)
        assert d <= 5.0


class TestRetryDecorator:
    def test_succeeds_without_retry(self):
        from cogscope.providers.retry import RetryConfig, retry_with_backoff

        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3))
        def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert fn() == "ok"
        assert call_count == 1

    def test_retries_on_failure(self):
        from cogscope.providers.retry import RetryConfig, retry_with_backoff

        call_count = 0

        @retry_with_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return "ok"

        assert fn() == "ok"
        assert call_count == 3


class TestRateLimiter:
    def test_acquire(self):
        from cogscope.providers.rate_limiter import RateLimitConfig, RateLimiter

        config = RateLimitConfig(requests_per_minute=600)
        rl = RateLimiter(config)
        assert rl.try_acquire()

    def test_stats(self):
        from cogscope.providers.rate_limiter import RateLimitConfig, RateLimiter

        config = RateLimitConfig(requests_per_minute=600)
        rl = RateLimiter(config)
        rl.acquire()
        stats = rl.stats
        assert "total_requests" in stats


class TestTokenAccountant:
    def test_record_and_report(self):
        from cogscope.core.models import TokenUsage
        from cogscope.providers.base import TokenAccountant

        accountant = TokenAccountant()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        accountant.record("gpt-4o", usage)
        # Check internal state
        assert accountant._usage["gpt-4o"]["calls"] == 1
        assert accountant._usage["gpt-4o"]["prompt_tokens"] == 100
        assert accountant._usage["gpt-4o"]["completion_tokens"] == 50

    def test_reset(self):
        from cogscope.core.models import TokenUsage
        from cogscope.providers.base import TokenAccountant

        accountant = TokenAccountant()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        accountant.record("gpt-4o", usage)
        accountant.reset()
        assert len(accountant._usage) == 0


class TestProviderConfig:
    def test_defaults(self):
        from cogscope.providers.base import ProviderConfig

        config = ProviderConfig(provider_name="openai", model="gpt-4o", api_key="sk-test")
        assert config.provider_name == "openai"
        assert config.model == "gpt-4o"
