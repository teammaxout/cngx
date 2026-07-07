"""Retry logic with exponential backoff, jitter, and circuit breaker.

Production-grade retry infrastructure for LLM provider calls.
Handles transient failures, rate limits, and provider outages.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Type

logger = logging.getLogger("cogscope.providers.retry")


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 1.0  # max jitter in seconds
    retryable_exceptions: tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)
    on_retry: Optional[Callable[[int, Exception, float], None]] = None


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # failures before opening
    recovery_timeout: float = 30.0  # seconds before half-open
    success_threshold: int = 2  # successes in half-open before closing


class CircuitBreaker:
    """Circuit breaker pattern for provider resilience.

    Prevents cascading failures by temporarily stopping calls
    to a failing provider.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.config.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
            return self._state

    def record_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info("Circuit breaker closed — provider recovered")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker re-opened — recovery failed")
            elif self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened after {self._failure_count} failures")

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN

    def reset(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, provider: str = "unknown"):
        super().__init__(
            f"Circuit breaker is OPEN for provider '{provider}'. "
            f"Too many consecutive failures. Requests are being rejected."
        )


def compute_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Compute delay for retry attempt with exponential backoff + jitter."""
    delay = config.base_delay * (config.exponential_base**attempt)
    delay = min(delay, config.max_delay)
    if config.jitter:
        jitter = random.uniform(0, config.jitter_max)
        delay += jitter
    return delay


def retry_with_backoff(
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
):
    """Decorator for retry with exponential backoff.

    Usage:
        @retry_with_backoff(RetryConfig(max_retries=3))
        def call_provider(prompt):
            ...
    """
    cfg = config or RetryConfig()

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if circuit_breaker and not circuit_breaker.allow_request():
                raise CircuitOpenError()

            last_exception: Exception | None = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if circuit_breaker:
                        circuit_breaker.record_success()
                    return result
                except cfg.retryable_exceptions as e:
                    last_exception = e
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    if attempt < cfg.max_retries:
                        delay = compute_delay(attempt, cfg)
                        logger.warning(
                            f"Retry {attempt + 1}/{cfg.max_retries} after "
                            f"{delay:.1f}s — {type(e).__name__}: {e}"
                        )
                        if cfg.on_retry:
                            cfg.on_retry(attempt + 1, e, delay)
                        time.sleep(delay)
                    else:
                        raise
                except Exception as e:
                    if circuit_breaker:
                        circuit_breaker.record_failure()
                    # Check if it's an HTTP error with retryable status
                    status = getattr(e, "status_code", None) or getattr(e, "status", None)
                    if status and status in cfg.retryable_status_codes:
                        last_exception = e
                        if attempt < cfg.max_retries:
                            delay = compute_delay(attempt, cfg)
                            # Special handling for 429 — respect Retry-After
                            retry_after = getattr(e, "retry_after", None)
                            if retry_after:
                                delay = max(delay, float(retry_after))
                            logger.warning(
                                f"Retry {attempt + 1}/{cfg.max_retries} after "
                                f"{delay:.1f}s — HTTP {status}"
                            )
                            if cfg.on_retry:
                                cfg.on_retry(attempt + 1, e, delay)
                            time.sleep(delay)
                        else:
                            raise
                    else:
                        raise

            if last_exception:
                raise last_exception

        return wrapper

    return decorator


async def async_retry_with_backoff(
    func: Callable,
    config: RetryConfig | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    *args,
    **kwargs,
) -> Any:
    """Async retry with exponential backoff."""
    import asyncio

    cfg = config or RetryConfig()

    if circuit_breaker and not circuit_breaker.allow_request():
        raise CircuitOpenError()

    last_exception: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if circuit_breaker:
                circuit_breaker.record_success()
            return result
        except cfg.retryable_exceptions as e:
            last_exception = e
            if circuit_breaker:
                circuit_breaker.record_failure()
            if attempt < cfg.max_retries:
                delay = compute_delay(attempt, cfg)
                logger.warning(
                    f"Async retry {attempt + 1}/{cfg.max_retries} after "
                    f"{delay:.1f}s — {type(e).__name__}: {e}"
                )
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            if circuit_breaker:
                circuit_breaker.record_failure()
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            if status and status in cfg.retryable_status_codes:
                last_exception = e
                if attempt < cfg.max_retries:
                    delay = compute_delay(attempt, cfg)
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after:
                        delay = max(delay, float(retry_after))
                    await asyncio.sleep(delay)
                else:
                    raise
            else:
                raise

    if last_exception:
        raise last_exception
