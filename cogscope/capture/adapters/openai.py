"""OpenAI-compatible adapter for Cogscope."""

import json
import time
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional

from openai import AsyncOpenAI, OpenAI

from cogscope.capture.adapters.base import BaseAdapter, StreamChunk
from cogscope.core.exceptions import AdapterError
from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall


class OpenAIAdapter(BaseAdapter):
    """Adapter for OpenAI and OpenAI-compatible APIs.

    Supports:
    - OpenAI API (GPT-4, GPT-4o, etc.)
    - Any OpenAI-compatible endpoint (Azure, local models, etc.)
    - Tool/function calling
    - Reasoning token extraction (where available)
    """

    adapter_type: str = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs: Any,
    ):
        super().__init__(model, **kwargs)
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    async def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Execute an async OpenAI call and capture the trace."""
        start_time = time.time()

        # Build messages
        msg_list = self._build_messages(prompt, system_message, messages)

        # Merge config with kwargs
        call_params = self._build_params(msg_list, tools, **kwargs)

        try:
            response = await self.async_client.chat.completions.create(**call_params)
            latency_ms = (time.time() - start_time) * 1000

            return self._build_trace(
                trace_id=self._create_trace_id(task_id),
                task_id=task_id,
                prompt=prompt,
                system_message=system_message,
                messages=msg_list,
                response=response,
                latency_ms=latency_ms,
            )
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"OpenAI call failed: {e}") from e

    def call_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Execute a synchronous OpenAI call and capture the trace."""
        start_time = time.time()

        # Build messages
        msg_list = self._build_messages(prompt, system_message, messages)

        # Merge config with kwargs
        call_params = self._build_params(msg_list, tools, **kwargs)

        try:
            response = self.client.chat.completions.create(**call_params)
            latency_ms = (time.time() - start_time) * 1000

            return self._build_trace(
                trace_id=self._create_trace_id(task_id),
                task_id=task_id,
                prompt=prompt,
                system_message=system_message,
                messages=msg_list,
                response=response,
                latency_ms=latency_ms,
            )
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"OpenAI call failed: {e}") from e

    def _build_messages(
        self,
        prompt: str,
        system_message: Optional[str],
        messages: Optional[list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Build message list for the API."""
        msg_list = []

        if system_message:
            msg_list.append({"role": "system", "content": system_message})

        if messages:
            msg_list.extend(messages)

        msg_list.append({"role": "user", "content": prompt})
        return msg_list

    def _build_params(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build API call parameters."""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", self.config.top_p),
        }

        if self.config.max_tokens:
            params["max_tokens"] = self.config.max_tokens
        if self.config.seed is not None:
            params["seed"] = self.config.seed
        if tools:
            params["tools"] = tools

        # Include any extra params from config
        params.update(self.config.extra)

        return params

    def _build_trace(
        self,
        trace_id: str,
        task_id: str,
        prompt: str,
        system_message: Optional[str],
        messages: list[dict[str, Any]],
        response: Any,
        latency_ms: float,
    ) -> ReasoningTrace:
        """Build a ReasoningTrace from the API response."""
        choice = response.choices[0]
        message = choice.message

        # Extract tool calls
        tool_calls = self._extract_tool_calls(message)

        # Extract reasoning tokens (if available)
        reasoning_tokens, reasoning_content = self._extract_reasoning_tokens(response)

        # Build token usage
        usage = response.usage
        token_usage = TokenUsage(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            reasoning_tokens=len(reasoning_tokens),
        )

        return ReasoningTrace(
            id=trace_id,
            task_id=task_id,
            model=self.model,
            model_config_params=self.config,
            adapter_type=self.adapter_type,
            system_message=system_message,
            prompt=prompt,
            messages=messages,
            tool_calls=tool_calls,
            reasoning_tokens=reasoning_tokens,
            reasoning_content=reasoning_content,
            output=message.content or "",
            finish_reason=choice.finish_reason,
            latency_ms=latency_ms,
            token_usage=token_usage,
        )

    def _extract_tool_calls(self, message: Any) -> list[ToolCall]:
        """Extract tool calls from the response message."""
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {"raw": tc.function.arguments}

                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    )
                )
        return tool_calls

    def _extract_reasoning_tokens(self, response: Any) -> tuple[list[str], Optional[str]]:
        """Extract reasoning tokens from response.

        For models that expose chain-of-thought reasoning (like o1),
        this extracts the reasoning chain.
        """
        # Check for reasoning_content in the response (o1-style models)
        choice = response.choices[0]
        message = choice.message

        if hasattr(message, "reasoning_content") and message.reasoning_content:
            content = message.reasoning_content
            # Split into tokens/steps
            steps = [s.strip() for s in content.split("\n") if s.strip()]
            return steps, content

        # Try to extract from content if it has thinking markers
        if message.content:
            content = message.content
            if "<thinking>" in content and "</thinking>" in content:
                start = content.index("<thinking>") + len("<thinking>")
                end = content.index("</thinking>")
                reasoning = content[start:end]
                steps = [s.strip() for s in reasoning.split("\n") if s.strip()]
                return steps, reasoning

        return [], None

    async def call_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream an OpenAI response and yield chunks.

        Yields StreamChunk objects as tokens arrive. The final chunk
        has is_final=True and carries aggregated metadata.
        """
        msg_list = self._build_messages(prompt, system_message, messages)
        call_params = self._build_params(msg_list, tools, **kwargs)
        call_params["stream"] = True
        call_params["stream_options"] = {"include_usage": True}

        start_time = time.time()
        full_text = ""
        reasoning_text = ""
        finish_reason = None
        tool_call_parts: dict[int, dict[str, Any]] = {}
        usage_data = None

        try:
            stream = await self.async_client.chat.completions.create(**call_params)
            async for chunk in stream:
                if not chunk.choices and hasattr(chunk, "usage") and chunk.usage:
                    # Final chunk with usage stats
                    usage_data = chunk.usage
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                chunk_finish = chunk.choices[0].finish_reason

                # Accumulate text
                text_part = ""
                reasoning_part = ""

                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_part = delta.reasoning_content
                    reasoning_text += reasoning_part

                if delta.content:
                    text_part = delta.content
                    full_text += text_part

                # Accumulate tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_parts:
                            tool_call_parts[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_parts[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_parts[idx]["arguments"] += tc_delta.function.arguments

                if chunk_finish:
                    finish_reason = chunk_finish

                if text_part or reasoning_part:
                    yield StreamChunk(
                        text=text_part,
                        reasoning_text=reasoning_part,
                        is_final=False,
                        finish_reason=chunk_finish,
                    )

            # Build final tool calls
            final_tool_calls: list[ToolCall] = []
            for _idx, tc in sorted(tool_call_parts.items()):
                try:
                    args = json.loads(tc["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {"raw": tc.get("arguments", "")}
                final_tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments=args,
                    )
                )

            # Build token usage
            token_usage = None
            if usage_data:
                token_usage = TokenUsage(
                    prompt_tokens=usage_data.prompt_tokens or 0,
                    completion_tokens=usage_data.completion_tokens or 0,
                    total_tokens=usage_data.total_tokens or 0,
                    reasoning_tokens=getattr(usage_data, "completion_tokens_details", None)
                    and getattr(usage_data.completion_tokens_details, "reasoning_tokens", 0)
                    or 0,
                )

            latency_ms = (time.time() - start_time) * 1000

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
                        model_config_params=self.config,
                        adapter_type=self.adapter_type,
                        system_message=system_message,
                        prompt=prompt,
                        messages=msg_list,
                        tool_calls=final_tool_calls,
                        reasoning_tokens=[reasoning_text] if reasoning_text else [],
                        reasoning_content=reasoning_text or None,
                        output=full_text,
                        finish_reason=finish_reason or "stop",
                        latency_ms=latency_ms,
                        token_usage=token_usage
                        or TokenUsage(
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                        ),
                    ),
                    "full_text": full_text,
                    "reasoning_text": reasoning_text,
                    "tool_calls": final_tool_calls,
                    "latency_ms": latency_ms,
                },
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"OpenAI stream failed: {e}") from e

    def call_stream_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Synchronous streaming via OpenAI.

        Yields StreamChunk objects as tokens arrive.
        """
        msg_list = self._build_messages(prompt, system_message, messages)
        call_params = self._build_params(msg_list, tools, **kwargs)
        call_params["stream"] = True
        call_params["stream_options"] = {"include_usage": True}

        start_time = time.time()
        full_text = ""
        reasoning_text = ""
        finish_reason = None
        tool_call_parts: dict[int, dict[str, Any]] = {}
        usage_data = None

        try:
            stream = self.client.chat.completions.create(**call_params)
            for chunk in stream:
                if not chunk.choices and hasattr(chunk, "usage") and chunk.usage:
                    usage_data = chunk.usage
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                chunk_finish = chunk.choices[0].finish_reason

                text_part = ""
                reasoning_part = ""

                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_part = delta.reasoning_content
                    reasoning_text += reasoning_part

                if delta.content:
                    text_part = delta.content
                    full_text += text_part

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_parts:
                            tool_call_parts[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_parts[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_parts[idx]["arguments"] += tc_delta.function.arguments

                if chunk_finish:
                    finish_reason = chunk_finish

                if text_part or reasoning_part:
                    yield StreamChunk(
                        text=text_part,
                        reasoning_text=reasoning_part,
                        is_final=False,
                        finish_reason=chunk_finish,
                    )

            # Build final tool calls
            final_tool_calls: list[ToolCall] = []
            for _idx, tc in sorted(tool_call_parts.items()):
                try:
                    args = json.loads(tc["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {"raw": tc.get("arguments", "")}
                final_tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments=args,
                    )
                )

            token_usage = None
            if usage_data:
                token_usage = TokenUsage(
                    prompt_tokens=usage_data.prompt_tokens or 0,
                    completion_tokens=usage_data.completion_tokens or 0,
                    total_tokens=usage_data.total_tokens or 0,
                )

            latency_ms = (time.time() - start_time) * 1000

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
                        model_config_params=self.config,
                        adapter_type=self.adapter_type,
                        system_message=system_message,
                        prompt=prompt,
                        messages=msg_list,
                        tool_calls=final_tool_calls,
                        reasoning_tokens=[reasoning_text] if reasoning_text else [],
                        reasoning_content=reasoning_text or None,
                        output=full_text,
                        finish_reason=finish_reason or "stop",
                        latency_ms=latency_ms,
                        token_usage=token_usage
                        or TokenUsage(
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                        ),
                    ),
                    "full_text": full_text,
                    "reasoning_text": reasoning_text,
                    "tool_calls": final_tool_calls,
                    "latency_ms": latency_ms,
                },
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"OpenAI sync stream failed: {e}") from e
