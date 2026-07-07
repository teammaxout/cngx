"""Anthropic Claude adapter for Cogscope.

Supports all Claude models:
- Claude Opus, Sonnet, Haiku (3, 3.5, 4 families)
- Extended thinking (where available)
- Tool use
- Streaming and non-streaming

Requires: pip install anthropic
"""

import re
import time
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional

from cogscope.capture.adapters.base import BaseAdapter, StreamChunk
from cogscope.core.exceptions import AdapterError
from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall

# Model aliases for convenience
_MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-haiku-3-20250519",
    "claude-4-opus": "claude-opus-4-20250514",
    "claude-4-sonnet": "claude-sonnet-4-20250514",
    "claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3.5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-opus": "claude-3-opus-20240229",
    "claude-3-sonnet": "claude-3-sonnet-20240229",
    "claude-3-haiku": "claude-3-haiku-20240307",
}


class ClaudeAdapter(BaseAdapter):
    """Adapter for Anthropic Claude models.

    Supports:
    - All Claude model families (Opus, Sonnet, Haiku)
    - Tool/function calling
    - Extended thinking extraction
    - Sync and async operation

    Usage:
        adapter = ClaudeAdapter(model="claude-sonnet-4-20250514")
        trace = adapter.call_sync(prompt="Solve: 2x + 3 = 7")
    """

    adapter_type: str = "claude"

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ):
        # Resolve aliases
        resolved = _MODEL_ALIASES.get(model, model)
        super().__init__(resolved, **kwargs)

        try:
            import anthropic
        except ImportError:
            raise AdapterError("Anthropic SDK not installed. Install with: pip install anthropic")

        self.client = anthropic.Anthropic(api_key=api_key)
        self.async_client = anthropic.AsyncAnthropic(api_key=api_key)
        self.max_tokens = max_tokens

    async def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Execute an async Claude call and capture the trace."""
        start_time = time.time()

        # Build messages
        msgs = self._build_messages(prompt, messages)

        # Build request kwargs
        request_kwargs = self._build_request_kwargs(msgs, system_message, tools, **kwargs)

        try:
            response = await self.async_client.messages.create(**request_kwargs)
            return self._process_response(
                response, prompt, system_message, msgs, tools, task_id, start_time
            )
        except Exception as e:
            raise AdapterError(f"Claude API call failed: {e}")

    def call_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Execute a synchronous Claude call and capture the trace."""
        start_time = time.time()

        # Build messages
        msgs = self._build_messages(prompt, messages)

        # Build request kwargs
        request_kwargs = self._build_request_kwargs(msgs, system_message, tools, **kwargs)

        try:
            response = self.client.messages.create(**request_kwargs)
            return self._process_response(
                response, prompt, system_message, msgs, tools, task_id, start_time
            )
        except Exception as e:
            raise AdapterError(f"Claude API call failed: {e}")

    def _build_messages(
        self,
        prompt: str,
        messages: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        """Build Claude message list."""
        if messages:
            # Ensure the last message is from the user
            msgs = list(messages)
            if msgs[-1].get("role") != "user":
                msgs.append({"role": "user", "content": prompt})
            return msgs
        return [{"role": "user", "content": prompt}]

    def _build_request_kwargs(
        self,
        messages: list[dict[str, Any]],
        system_message: Optional[str],
        tools: Optional[list[dict[str, Any]]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the kwargs dict for the Anthropic API call."""
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
        }

        # System message is a top-level param in Anthropic API
        if system_message:
            request_kwargs["system"] = system_message

        # Convert tools from OpenAI format to Claude format
        if tools:
            request_kwargs["tools"] = self._convert_tools(tools)

        # Temperature, top_p, etc.
        if self.config.temperature is not None:
            request_kwargs["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            request_kwargs["top_p"] = self.config.top_p

        # Pass through any extra kwargs
        request_kwargs.update(kwargs)

        return request_kwargs

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-format tools to Anthropic format.

        OpenAI format:
            {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Anthropic format:
            {"name": ..., "description": ..., "input_schema": ...}
        """
        converted = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                converted.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get(
                            "parameters", {"type": "object", "properties": {}}
                        ),
                    }
                )
            elif "name" in tool:
                # Already in Anthropic format
                converted.append(tool)
        return converted

    def _process_response(
        self,
        response: Any,
        prompt: str,
        system_message: Optional[str],
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        task_id: str,
        start_time: float,
    ) -> ReasoningTrace:
        """Process a Claude response into a ReasoningTrace."""
        latency_ms = (time.time() - start_time) * 1000

        # Extract text content and reasoning
        output_text = ""
        reasoning_content = ""
        tool_calls: list[ToolCall] = []
        reasoning_tokens: list[str] = []

        for block in response.content:
            if block.type == "text":
                output_text += block.text
            elif block.type == "thinking":
                # Claude extended thinking
                reasoning_content += block.thinking
                reasoning_tokens.append(block.thinking)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        # If no explicit thinking block, try to extract from <thinking> tags
        if not reasoning_content and output_text:
            reasoning_content = self._extract_thinking_tags(output_text)
            if reasoning_content:
                reasoning_tokens = [reasoning_content]

        # Build token usage
        usage = response.usage
        token_usage = TokenUsage(
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.input_tokens + usage.output_tokens,
            reasoning_tokens=getattr(usage, "cache_creation_input_tokens", 0),
        )

        # Build trace
        trace = ReasoningTrace(
            id=self._create_trace_id(task_id),
            task_id=task_id,
            model=self.model,
            adapter_type=self.adapter_type,
            system_message=system_message,
            prompt=prompt,
            messages=messages,
            tool_calls=tool_calls,
            reasoning_tokens=reasoning_tokens,
            reasoning_content=reasoning_content,
            output=output_text,
            finish_reason=response.stop_reason or "end_turn",
            latency_ms=latency_ms,
            token_usage=token_usage,
            metadata={
                "claude_model": response.model,
                "claude_stop_reason": response.stop_reason,
                "claude_id": response.id,
            },
            timestamp=datetime.utcnow(),
        )

        return trace

    def _extract_thinking_tags(self, text: str) -> str:
        """Extract content from <thinking>...</thinking> tags."""
        pattern = r"<thinking>(.*?)</thinking>"
        matches = re.findall(pattern, text, re.DOTALL)
        return "\n".join(matches)

    async def call_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a Claude response and yield chunks.

        Uses Anthropic's streaming messages API. Yields text and
        thinking blocks as StreamChunk objects.
        """
        msgs = self._build_messages(prompt, messages)
        request_kwargs = self._build_request_kwargs(msgs, system_message, tools, **kwargs)
        request_kwargs["stream"] = True

        start_time = time.time()
        full_text = ""
        reasoning_text = ""
        finish_reason = None
        tool_calls: list[ToolCall] = []
        current_tool: Optional[dict[str, Any]] = None
        input_tokens = 0
        output_tokens = 0

        try:
            async with self.async_client.messages.stream(
                **{k: v for k, v in request_kwargs.items() if k != "stream"}
            ) as stream:
                async for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "tool_use":
                                current_tool = {
                                    "id": block.id,
                                    "name": block.name,
                                    "input_json": "",
                                }
                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                full_text += delta.text
                                yield StreamChunk(
                                    text=delta.text,
                                    is_final=False,
                                )
                            elif delta.type == "thinking_delta":
                                reasoning_text += delta.thinking
                                yield StreamChunk(
                                    reasoning_text=delta.thinking,
                                    is_final=False,
                                )
                            elif delta.type == "input_json_delta" and current_tool:
                                current_tool["input_json"] += delta.partial_json
                        elif event.type == "content_block_stop":
                            if current_tool:
                                import json as _json

                                try:
                                    args = _json.loads(current_tool["input_json"])
                                except (ValueError, KeyError):
                                    args = {"raw": current_tool.get("input_json", "")}
                                tool_calls.append(
                                    ToolCall(
                                        id=current_tool["id"],
                                        name=current_tool["name"],
                                        arguments=args,
                                    )
                                )
                                current_tool = None
                        elif event.type == "message_delta":
                            if hasattr(event, "delta") and hasattr(event.delta, "stop_reason"):
                                finish_reason = event.delta.stop_reason
                            if hasattr(event, "usage"):
                                output_tokens = getattr(event.usage, "output_tokens", 0)
                        elif event.type == "message_start":
                            if hasattr(event, "message") and hasattr(event.message, "usage"):
                                input_tokens = event.message.usage.input_tokens

            latency_ms = (time.time() - start_time) * 1000

            token_usage = TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

            yield StreamChunk(
                text="",
                reasoning_text="",
                is_final=True,
                finish_reason=finish_reason,
                metadata={
                    "trace": ReasoningTrace(
                        id=self._create_trace_id(task_id),
                        task_id=task_id,
                        model=self.model,
                        adapter_type=self.adapter_type,
                        system_message=system_message,
                        prompt=prompt,
                        messages=msgs,
                        tool_calls=tool_calls,
                        reasoning_tokens=[reasoning_text] if reasoning_text else [],
                        reasoning_content=reasoning_text or None,
                        output=full_text,
                        finish_reason=finish_reason or "end_turn",
                        latency_ms=latency_ms,
                        token_usage=token_usage,
                        metadata={"claude_model": self.model},
                        timestamp=datetime.utcnow(),
                    ),
                    "full_text": full_text,
                    "reasoning_text": reasoning_text,
                    "tool_calls": tool_calls,
                    "latency_ms": latency_ms,
                },
            )

        except Exception as e:
            raise AdapterError(f"Claude stream failed: {e}")

    def call_stream_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Synchronous streaming via Claude.

        Uses Anthropic's synchronous streaming messages API.
        """
        msgs = self._build_messages(prompt, messages)
        request_kwargs = self._build_request_kwargs(msgs, system_message, tools, **kwargs)

        start_time = time.time()
        full_text = ""
        reasoning_text = ""
        finish_reason = None
        tool_calls: list[ToolCall] = []
        current_tool: Optional[dict[str, Any]] = None
        input_tokens = 0
        output_tokens = 0

        try:
            with self.client.messages.stream(**{k: v for k, v in request_kwargs.items()}) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "tool_use":
                                current_tool = {
                                    "id": block.id,
                                    "name": block.name,
                                    "input_json": "",
                                }
                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                full_text += delta.text
                                yield StreamChunk(
                                    text=delta.text,
                                    is_final=False,
                                )
                            elif delta.type == "thinking_delta":
                                reasoning_text += delta.thinking
                                yield StreamChunk(
                                    reasoning_text=delta.thinking,
                                    is_final=False,
                                )
                            elif delta.type == "input_json_delta" and current_tool:
                                current_tool["input_json"] += delta.partial_json
                        elif event.type == "content_block_stop":
                            if current_tool:
                                import json as _json

                                try:
                                    args = _json.loads(current_tool["input_json"])
                                except (ValueError, KeyError):
                                    args = {"raw": current_tool.get("input_json", "")}
                                tool_calls.append(
                                    ToolCall(
                                        id=current_tool["id"],
                                        name=current_tool["name"],
                                        arguments=args,
                                    )
                                )
                                current_tool = None
                        elif event.type == "message_delta":
                            if hasattr(event, "delta") and hasattr(event.delta, "stop_reason"):
                                finish_reason = event.delta.stop_reason
                            if hasattr(event, "usage"):
                                output_tokens = getattr(event.usage, "output_tokens", 0)
                        elif event.type == "message_start":
                            if hasattr(event, "message") and hasattr(event.message, "usage"):
                                input_tokens = event.message.usage.input_tokens

            latency_ms = (time.time() - start_time) * 1000

            token_usage = TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )

            yield StreamChunk(
                text="",
                reasoning_text="",
                is_final=True,
                finish_reason=finish_reason,
                metadata={
                    "trace": ReasoningTrace(
                        id=self._create_trace_id(task_id),
                        task_id=task_id,
                        model=self.model,
                        adapter_type=self.adapter_type,
                        system_message=system_message,
                        prompt=prompt,
                        messages=msgs,
                        tool_calls=tool_calls,
                        reasoning_tokens=[reasoning_text] if reasoning_text else [],
                        reasoning_content=reasoning_text or None,
                        output=full_text,
                        finish_reason=finish_reason or "end_turn",
                        latency_ms=latency_ms,
                        token_usage=token_usage,
                        metadata={"claude_model": self.model},
                        timestamp=datetime.utcnow(),
                    ),
                    "full_text": full_text,
                    "reasoning_text": reasoning_text,
                    "tool_calls": tool_calls,
                    "latency_ms": latency_ms,
                },
            )

        except Exception as e:
            raise AdapterError(f"Claude sync stream failed: {e}")
