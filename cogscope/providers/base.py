"""Provider abstraction layer.

Standardized interface for LLM providers with built-in
retry, rate limiting, circuit breaking, and token accounting.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from cogscope.core.models import ReasoningTrace, TokenUsage
from cogscope.providers.rate_limiter import RateLimitConfig, RateLimiter
from cogscope.providers.retry import (
    CircuitBreaker,
    CircuitBreakerConfig,
    RetryConfig,
    retry_with_backoff,
)

logger = logging.getLogger("cogscope.providers")


@dataclass
class ProviderConfig:
    """Configuration for a provider instance."""

    provider_name: str = "unknown"
    model: str = ""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 120.0
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)


@dataclass
class ProviderResult:
    """Result from a provider call with accounting metadata."""

    trace: ReasoningTrace
    provider: str
    latency_ms: float
    token_usage: TokenUsage
    attempt_count: int = 1
    was_retried: bool = False
    cached: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


class TokenAccountant:
    """Track token usage across providers.

    Thread-safe accumulator for cost and usage tracking.
    """

    # Approximate cost per 1K tokens (USD) — June 2025 estimates
    COST_PER_1K: dict[str, dict[str, float]] = {
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "o1": {"input": 0.015, "output": 0.06},
        "o3-mini": {"input": 0.0011, "output": 0.0044},
        "gemini-2.5-flash": {"input": 0.00015, "output": 0.001},
        "gemini-2.5-pro": {"input": 0.00125, "output": 0.01},
        "claude-sonnet": {"input": 0.003, "output": 0.015},
        "claude-opus": {"input": 0.015, "output": 0.075},
        "claude-haiku": {"input": 0.00025, "output": 0.00125},
    }

    def __init__(self):
        self._usage: dict[str, dict[str, int]] = {}
        self._costs: dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, model: str, usage: TokenUsage) -> None:
        """Record token usage for a model."""
        with self._lock:
            if model not in self._usage:
                self._usage[model] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "reasoning_tokens": 0,
                    "calls": 0,
                }
            self._usage[model]["prompt_tokens"] += usage.prompt_tokens
            self._usage[model]["completion_tokens"] += usage.completion_tokens
            self._usage[model]["total_tokens"] += usage.total_tokens
            self._usage[model]["reasoning_tokens"] += usage.reasoning_tokens
            self._usage[model]["calls"] += 1

            # Estimate cost
            cost = self._estimate_cost(model, usage)
            self._costs[model] = self._costs.get(model, 0.0) + cost

    def _estimate_cost(self, model: str, usage: TokenUsage) -> float:
        """Estimate cost for a single call."""
        # Find matching cost entry
        cost_key = None
        model_lower = model.lower()
        for key in self.COST_PER_1K:
            if key in model_lower:
                cost_key = key
                break
        if not cost_key:
            return 0.0

        rates = self.COST_PER_1K[cost_key]
        input_cost = (usage.prompt_tokens / 1000) * rates.get("input", 0)
        output_cost = (usage.completion_tokens / 1000) * rates.get("output", 0)
        return input_cost + output_cost

    def get_report(self) -> dict[str, Any]:
        """Get usage and cost report."""
        with self._lock:
            total_cost = sum(self._costs.values())
            total_tokens = sum(u["total_tokens"] for u in self._usage.values())
            total_calls = sum(u["calls"] for u in self._usage.values())
            return {
                "per_model": dict(self._usage),
                "costs": dict(self._costs),
                "total_cost_usd": total_cost,
                "total_tokens": total_tokens,
                "total_calls": total_calls,
            }

    def reset(self) -> None:
        with self._lock:
            self._usage.clear()
            self._costs.clear()


# Global token accountant
_accountant = TokenAccountant()


def get_token_accountant() -> TokenAccountant:
    return _accountant
