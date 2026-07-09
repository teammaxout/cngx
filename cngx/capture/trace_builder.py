"""Build reasoning traces from existing agent output without LLM calls."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from cngx.core.models import ReasoningTrace, TokenUsage


def build_trace_from_text(
    prompt: str,
    output: str,
    *,
    task_id: str = "policy_check",
    model: str = "agent-output",
    adapter_type: str = "offline",
    reasoning_content: Optional[str] = None,
    reasoning_tokens: Optional[list[str]] = None,
    trace_id: Optional[str] = None,
) -> ReasoningTrace:
    """Construct a ReasoningTrace from prompt and agent output text.

    No LLM adapter is invoked. Use this to fingerprint and gate output that
    already exists (file, stdin, or CI artifact) before trusting it.
    """
    completion_tokens = max(1, len(output.split()))
    return ReasoningTrace(
        id=trace_id or str(uuid.uuid4()),
        timestamp=datetime.utcnow(),
        task_id=task_id,
        model=model,
        adapter_type=adapter_type,
        prompt=prompt,
        output=output,
        reasoning_content=reasoning_content,
        reasoning_tokens=reasoning_tokens or [],
        token_usage=TokenUsage(
            prompt_tokens=max(1, len(prompt.split())),
            completion_tokens=completion_tokens,
            total_tokens=max(1, len(prompt.split())) + completion_tokens,
        ),
    )
