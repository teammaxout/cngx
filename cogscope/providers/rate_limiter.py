"""Token bucket rate limiter for LLM provider calls.

Thread-safe rate limiting with per-provider configuration.
Supports both request-per-minute and token-per-minute limits.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("cogscope.providers.rate_limiter")


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""

    requests_per_minute: float = 60.0
    tokens_per_minute: float = 100_000.0
    burst_multiplier: float = 1.5  # Allow bursts up to 1.5x rate


class TokenBucket:
    """Token bucket algorithm for rate limiting.

    Thread-safe. Supports both request and token rate limits.
    """

    def __init__(self, rate: float, capacity: float):
        """
        Args:
            rate: Tokens added per second
            capacity: Maximum tokens in bucket
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def consume(self, count: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if successful."""
        with self._lock:
            self._refill()
            if self._tokens >= count:
                self._tokens -= count
                return True
            return False

    def wait_and_consume(self, count: float = 1.0, timeout: float = 30.0) -> bool:
        """Wait until tokens are available, then consume. Returns False on timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.consume(count):
                return True
            # Calculate wait time
            with self._lock:
                self._refill()
                tokens_needed = count - self._tokens
                if tokens_needed <= 0:
                    continue
                wait_time = min(tokens_needed / self._rate, deadline - time.monotonic())
            if wait_time > 0:
                time.sleep(min(wait_time, 0.1))  # Max 100ms sleep intervals
        return False

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class RateLimiter:
    """Rate limiter for LLM provider calls.

    Manages both request rate and token rate limits.
    Thread-safe for concurrent access.

    Usage:
        limiter = RateLimiter(RateLimitConfig(requests_per_minute=60))
        limiter.acquire()  # blocks until allowed
        result = call_model(...)
        limiter.record_tokens(result.total_tokens)
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()

        # Request rate bucket
        rpm = self.config.requests_per_minute
        request_rate = rpm / 60.0  # per second
        request_capacity = rpm * self.config.burst_multiplier / 60.0
        self._request_bucket = TokenBucket(request_rate, request_capacity)

        # Token rate bucket
        tpm = self.config.tokens_per_minute
        token_rate = tpm / 60.0  # per second
        token_capacity = tpm * self.config.burst_multiplier / 60.0
        self._token_bucket = TokenBucket(token_rate, token_capacity)

        # Stats
        self._total_requests = 0
        self._total_tokens = 0
        self._throttled_count = 0
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire permission for one request. Blocks until allowed.

        Returns False if timeout exceeded.
        """
        acquired = self._request_bucket.wait_and_consume(1.0, timeout)
        if not acquired:
            with self._lock:
                self._throttled_count += 1
            logger.warning("Rate limiter: request throttled (timeout)")
        else:
            with self._lock:
                self._total_requests += 1
        return acquired

    def try_acquire(self) -> bool:
        """Non-blocking acquire. Returns immediately."""
        acquired = self._request_bucket.consume(1.0)
        if acquired:
            with self._lock:
                self._total_requests += 1
        return acquired

    def record_tokens(self, token_count: int) -> None:
        """Record tokens consumed. May cause future throttling."""
        self._token_bucket.consume(float(token_count))
        with self._lock:
            self._total_tokens += token_count

    def acquire_tokens(self, estimated_tokens: int, timeout: float = 30.0) -> bool:
        """Pre-acquire estimated tokens before a call."""
        return self._token_bucket.wait_and_consume(float(estimated_tokens), timeout)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "total_tokens": self._total_tokens,
                "throttled_count": self._throttled_count,
                "request_tokens_available": self._request_bucket.available,
                "token_tokens_available": self._token_bucket.available,
            }
