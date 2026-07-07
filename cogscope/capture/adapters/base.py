"""Base adapter interface for LLM backends."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional

from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall


class StreamChunk:
    """A single chunk from a streaming LLM response."""

    def __init__(
        self,
        text: str = "",
        reasoning_text: str = "",
        is_final: bool = False,
        tool_call: Optional[ToolCall] = None,
        finish_reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.text = text
        self.reasoning_text = reasoning_text
        self.is_final = is_final
        self.tool_call = tool_call
        self.finish_reason = finish_reason
        self.metadata = metadata or {}


class BaseAdapter(ABC):
    """Base class for LLM adapters.

    Adapters translate between Cogscope's trace format and specific LLM backends.
    Each adapter must implement the call() method to execute LLM requests
    and capture full reasoning traces.
    """

    adapter_type: str = "base"

    def __init__(self, model: str, **kwargs: Any):
        self.model = model
        self.config = ModelConfig(**kwargs) if kwargs else ModelConfig()

    @abstractmethod
    async def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Execute an LLM call and return a complete reasoning trace."""
        pass

    @abstractmethod
    def call_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Synchronous version of call()."""
        pass

    async def call_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream an LLM response and yield chunks.

        Default implementation falls back to non-streaming call.
        Override in subclasses for true streaming.

        Yields:
            StreamChunk objects with partial text.
            The final chunk has is_final=True.
        """
        # Default: fall back to non-streaming
        trace = await self.call(prompt, system_message, messages, tools, **kwargs)
        yield StreamChunk(
            text=trace.output,
            reasoning_text=trace.reasoning_content or "",
            is_final=True,
            finish_reason=trace.finish_reason,
        )

    def call_stream_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Synchronous streaming. Default falls back to non-streaming call."""
        trace = self.call_sync(prompt, system_message, messages, tools, **kwargs)
        yield StreamChunk(
            text=trace.output,
            reasoning_text=trace.reasoning_content or "",
            is_final=True,
            finish_reason=trace.finish_reason,
        )

    def _create_trace_id(self, task_id: str) -> str:
        """Generate a unique trace ID."""
        import uuid

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"trace_{task_id}_{timestamp}_{short_uuid}"

    def _extract_tool_calls(self, response: Any) -> list[ToolCall]:
        """Extract tool calls from a response. Override in subclasses."""
        return []

    def _extract_reasoning_tokens(self, response: Any) -> tuple[list[str], Optional[str]]:
        """Extract reasoning tokens from a response. Override in subclasses."""
        return [], None

    def update_config(self, **kwargs: Any) -> None:
        """Update the model configuration."""
        current = self.config.model_dump()
        current.update(kwargs)
        self.config = ModelConfig(**current)
