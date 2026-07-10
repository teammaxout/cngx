"""Google Gemini adapter for cngx.

This adapter supports all Google Gemini models via the Google AI Studio API.
It works with both free tier (gemini-2.5-flash) and paid models (gemini-pro).

Uses the modern ``google-genai`` SDK (>= 1.0).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional

try:
    from google import genai
    from google.genai import types as genai_types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

from cngx.capture.adapters.base import BaseAdapter, StreamChunk
from cngx.core.exceptions import AdapterError
from cngx.core.models import ModelConfig, ReasoningTrace, TokenUsage, ToolCall


class GeminiAdapter(BaseAdapter):
    """Adapter for Google Gemini models.

    Supports all Gemini models including:
    - gemini-1.5-flash (free tier, fast)
    - gemini-1.5-flash-8b (free tier, smaller)
    - gemini-1.5-pro (paid, most capable)
    - gemini-1.0-pro (legacy)
    - gemini-2.0-flash-exp (experimental)

    Usage:
        adapter = GeminiAdapter(model="gemini-1.5-flash")
        trace = adapter.call_sync(prompt="Explain quantum computing")
    """

    # Default: rolling flash alias. gemini-2.5-flash is blocked for many new keys.
    DEFAULT_MODEL = "gemini-flash-latest"

    # Model aliases for convenience
    MODEL_ALIASES = {
        "flash": "gemini-flash-latest",
        "flash-lite": "gemini-flash-lite-latest",
        "pro": "gemini-pro-latest",
        "flash-2": "gemini-2.0-flash",
        "flash-2.5": "gemini-2.5-flash",
        "flash-3.5": "gemini-3.5-flash",
    }

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        top_p: float = 0.95,
        top_k: int = 40,
        **kwargs: Any,
    ):
        """Initialize the Gemini adapter.

        Args:
            model: Model name or alias (e.g., "gemini-1.5-flash" or "flash")
            api_key: Google AI API key (or set GOOGLE_API_KEY env var)
            temperature: Sampling temperature (0.0-2.0)
            max_output_tokens: Maximum tokens in response
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter
            **kwargs: Additional configuration
        """
        if not GEMINI_AVAILABLE:
            raise AdapterError("Google GenAI package not installed. Run: pip install google-genai")

        # Resolve model alias
        resolved_model = self.MODEL_ALIASES.get(model, model)
        super().__init__(model=resolved_model)

        # Accept either env name; Google SDK docs use GOOGLE_API_KEY, many
        # projects (and this repo's .env.example) use GEMINI_API_KEY.
        self.api_key = (
            api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        )
        if not self.api_key:
            raise AdapterError(
                "Google API key required. Set GOOGLE_API_KEY or GEMINI_API_KEY "
                "or pass api_key parameter. Get a free key at https://aistudio.google.com"
            )

        # Create the modern Client (replaces genai.configure + GenerativeModel)
        self._client = genai.Client(api_key=self.api_key)

        # Store generation config
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.top_p = top_p
        self.top_k = top_k

        # Build reusable GenerateContentConfig
        self._gen_config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
            top_k=top_k,
        )

    def update_config(self, **kwargs: Any) -> None:
        """Update adapter configuration."""
        if "temperature" in kwargs:
            self.temperature = kwargs["temperature"]
        if "max_output_tokens" in kwargs:
            self.max_output_tokens = kwargs["max_output_tokens"]
        if "top_p" in kwargs:
            self.top_p = kwargs["top_p"]
        if "top_k" in kwargs:
            self.top_k = kwargs["top_k"]

        # Rebuild GenerateContentConfig
        self._gen_config = genai_types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            top_p=self.top_p,
            top_k=self.top_k,
        )

    async def call(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Make an async call to Gemini.

        Args:
            prompt: User prompt
            system_message: System instruction
            tools: Tool definitions (Gemini function calling format)
            task_id: Task identifier
            **kwargs: Additional parameters

        Returns:
            Complete reasoning trace
        """
        start_time = time.time()
        trace_id = self._create_trace_id(task_id)

        try:
            # Build content
            contents = self._build_contents(prompt, system_message)

            # Build per-call config (may include tools)
            config = self._make_call_config(tools)

            # Make async call with retry for rate limiting
            response = await self._call_with_retry_async(contents, config)

            latency_ms = (time.time() - start_time) * 1000

            return self._build_trace(
                trace_id=trace_id,
                task_id=task_id,
                prompt=prompt,
                system_message=system_message,
                response=response,
                latency_ms=latency_ms,
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"Gemini API call failed: {e}") from e

    def call_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Make a synchronous call to Gemini.

        Args:
            prompt: User prompt
            system_message: System instruction
            tools: Tool definitions
            task_id: Task identifier
            **kwargs: Additional parameters

        Returns:
            Complete reasoning trace
        """
        start_time = time.time()
        trace_id = self._create_trace_id(task_id)

        try:
            # Build content
            contents = self._build_contents(prompt, system_message)

            # Build per-call config (may include tools)
            config = self._make_call_config(tools)

            # Make sync call with retry for rate limiting
            response = self._call_with_retry(contents, config)

            latency_ms = (time.time() - start_time) * 1000

            return self._build_trace(
                trace_id=trace_id,
                task_id=task_id,
                prompt=prompt,
                system_message=system_message,
                response=response,
                latency_ms=latency_ms,
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"Gemini API call failed: {e}") from e

    def _call_with_retry(self, contents, config, max_retries: int = 3):
        """Call generate_content with retry on 429 rate limits."""
        logger = logging.getLogger("cngx.gemini")
        for attempt in range(max_retries + 1):
            try:
                return self._client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                err_str = str(e)
                is_rate_limit = (
                    "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
                )
                if is_rate_limit and attempt < max_retries:
                    # Parse retry-after from error if available, else use fixed 60s
                    import re as _re

                    match = _re.search(r"retry in (\d+(?:\.\d+)?)", err_str, _re.I)
                    wait = float(match.group(1)) + 2 if match else 62.0
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{max_retries}), waiting {wait:.0f}s"
                    )
                    time.sleep(wait)
                    continue
                raise

    async def _call_with_retry_async(self, contents, config, max_retries: int = 3):
        """Call generate_content_async with retry on 429 rate limits."""
        logger = logging.getLogger("cngx.gemini")
        for attempt in range(max_retries + 1):
            try:
                return await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                err_str = str(e)
                is_rate_limit = (
                    "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
                )
                if is_rate_limit and attempt < max_retries:
                    import re as _re

                    match = _re.search(r"retry in (\d+(?:\.\d+)?)", err_str, _re.I)
                    wait = float(match.group(1)) + 2 if match else 62.0
                    logger.warning(
                        f"Rate limited (attempt {attempt + 1}/{max_retries}), waiting {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

    def _build_contents(
        self,
        prompt: str,
        system_message: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Build Gemini content format."""
        contents = []

        # System instructions are now passed via GenerateContentConfig,
        # so we only send the user prompt as content.
        if system_message:
            # Prepend system context for older models or as fallback
            full_prompt = f"{system_message}\n\n{prompt}"
        else:
            full_prompt = prompt

        contents.append({"role": "user", "parts": [{"text": full_prompt}]})

        return contents

    def _make_call_config(
        self,
        tools: Optional[list[dict[str, Any]]] = None,
    ) -> genai_types.GenerateContentConfig:
        """Build a per-call GenerateContentConfig, optionally including tools."""
        if not tools:
            return self._gen_config

        gemini_tools = self._convert_tools(tools)
        return genai_types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            top_p=self.top_p,
            top_k=self.top_k,
            tools=gemini_tools,
        )

    def _convert_tools(
        self,
        tools: list[dict[str, Any]],
    ) -> list[genai_types.Tool]:
        """Convert OpenAI-style tools to Gemini Tool objects."""
        gemini_tools: list[genai_types.Tool] = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                gemini_tools.append(
                    genai_types.Tool(
                        function_declarations=[
                            genai_types.FunctionDeclaration(
                                name=func.get("name", ""),
                                description=func.get("description", ""),
                                parameters=func.get("parameters", {}),
                            )
                        ]
                    )
                )

        return gemini_tools

    def _build_trace(
        self,
        trace_id: str,
        task_id: str,
        prompt: str,
        system_message: Optional[str],
        response: "genai_types.GenerateContentResponse",
        latency_ms: float,
    ) -> ReasoningTrace:
        """Build a ReasoningTrace from Gemini response."""
        # Extract text output
        try:
            output_text = response.text
        except ValueError:
            # Response might be blocked or empty
            output_text = ""
            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "text"):
                                output_text += part.text

        # Extract tool calls if any
        tool_calls = self._extract_tool_calls(response)

        # Extract token usage
        token_usage = self._extract_token_usage(response)

        # Get finish reason
        finish_reason = self._get_finish_reason(response)

        # Build messages list
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": output_text},
        ]

        return ReasoningTrace(
            id=trace_id,
            task_id=task_id,
            model=self.model,
            model_config_params=ModelConfig(
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
                top_p=self.top_p,
            ),
            adapter_type="gemini",
            system_message=system_message,
            prompt=prompt,
            messages=messages,
            tool_calls=tool_calls,
            reasoning_tokens=[],  # Gemini doesn't expose reasoning tokens
            reasoning_content=None,
            output=output_text,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            token_usage=token_usage,
            metadata={
                "adapter": "gemini",
                "model": self.model,
                "safety_ratings": self._get_safety_ratings(response),
            },
            timestamp=datetime.now(),
        )

    def _extract_tool_calls(
        self,
        response: "genai_types.GenerateContentResponse",
    ) -> list[ToolCall]:
        """Extract tool calls from Gemini response."""
        tool_calls = []

        if not response.candidates:
            return tool_calls

        for candidate in response.candidates:
            if not candidate.content or not candidate.content.parts:
                continue

            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=f"call_{fc.name}_{len(tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                            result=None,  # Would be filled by tool execution
                        )
                    )

        return tool_calls

    def _extract_token_usage(
        self,
        response: "genai_types.GenerateContentResponse",
    ) -> TokenUsage:
        """Extract token usage from Gemini response."""
        try:
            usage = response.usage_metadata
            return TokenUsage(
                prompt_tokens=usage.prompt_token_count or 0,
                completion_tokens=usage.candidates_token_count or 0,
                total_tokens=usage.total_token_count or 0,
            )
        except (AttributeError, TypeError):
            return TokenUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

    def _get_finish_reason(
        self,
        response: "genai_types.GenerateContentResponse",
    ) -> str:
        """Get finish reason from response."""
        try:
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason") and candidate.finish_reason:
                    fr = candidate.finish_reason
                    # New SDK may return a string or an enum with .name
                    return str(fr.name) if hasattr(fr, "name") else str(fr)
        except (AttributeError, IndexError):
            pass
        return "unknown"

    def _get_safety_ratings(
        self,
        response: "genai_types.GenerateContentResponse",
    ) -> list[dict[str, str]]:
        """Extract safety ratings from response."""
        ratings = []
        try:
            if response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "safety_ratings") and candidate.safety_ratings:
                    for rating in candidate.safety_ratings:
                        cat = rating.category
                        prob = rating.probability
                        ratings.append(
                            {
                                "category": str(cat.name) if hasattr(cat, "name") else str(cat),
                                "probability": (
                                    str(prob.name) if hasattr(prob, "name") else str(prob)
                                ),
                            }
                        )
        except (AttributeError, IndexError):
            pass
        return ratings

    async def call_stream(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a Gemini response and yield chunks.

        Uses the new google-genai generate_content_stream API.
        """
        start_time = time.time()
        contents = self._build_contents(prompt, system_message)
        config = self._make_call_config(tools)

        full_text = ""
        try:
            async for chunk in self._client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            ):
                text_part = ""
                try:
                    if chunk.text:
                        text_part = chunk.text
                        full_text += text_part
                except (ValueError, AttributeError):
                    pass

                if text_part:
                    yield StreamChunk(
                        text=text_part,
                        is_final=False,
                    )

            # Resolve the full response for metadata
            latency_ms = (time.time() - start_time) * 1000

            # Build a minimal trace from accumulated data
            tool_calls = self._extract_tool_calls_from_text(full_text)
            finish_reason = "STOP"

            # Token usage is not reliably available in streaming mode
            token_usage = TokenUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

            msgs = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": full_text},
            ]

            yield StreamChunk(
                text="",
                is_final=True,
                finish_reason=finish_reason,
                metadata={
                    "trace": ReasoningTrace(
                        id=self._create_trace_id(task_id),
                        task_id=task_id,
                        model=self.model,
                        model_config_params=ModelConfig(
                            temperature=self.temperature,
                            max_tokens=self.max_output_tokens,
                            top_p=self.top_p,
                        ),
                        adapter_type="gemini",
                        system_message=system_message,
                        prompt=prompt,
                        messages=msgs,
                        tool_calls=tool_calls,
                        reasoning_tokens=[],
                        reasoning_content=None,
                        output=full_text,
                        finish_reason=finish_reason,
                        latency_ms=latency_ms,
                        token_usage=token_usage,
                        metadata={"adapter": "gemini", "model": self.model},
                        timestamp=datetime.now(),
                    ),
                    "full_text": full_text,
                    "latency_ms": latency_ms,
                },
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"Gemini stream failed: {e}") from e

    def call_stream_sync(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        task_id: str = "default",
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Synchronous streaming via Gemini."""
        start_time = time.time()
        contents = self._build_contents(prompt, system_message)
        config = self._make_call_config(tools)

        full_text = ""
        try:
            for chunk in self._client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            ):
                text_part = ""
                try:
                    if chunk.text:
                        text_part = chunk.text
                        full_text += text_part
                except (ValueError, AttributeError):
                    pass

                if text_part:
                    yield StreamChunk(
                        text=text_part,
                        is_final=False,
                    )

            latency_ms = (time.time() - start_time) * 1000
            tool_calls = self._extract_tool_calls_from_text(full_text)
            finish_reason = "STOP"

            token_usage = TokenUsage(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )

            msgs = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": full_text},
            ]

            yield StreamChunk(
                text="",
                is_final=True,
                finish_reason=finish_reason,
                metadata={
                    "trace": ReasoningTrace(
                        id=self._create_trace_id(task_id),
                        task_id=task_id,
                        model=self.model,
                        model_config_params=ModelConfig(
                            temperature=self.temperature,
                            max_tokens=self.max_output_tokens,
                            top_p=self.top_p,
                        ),
                        adapter_type="gemini",
                        system_message=system_message,
                        prompt=prompt,
                        messages=msgs,
                        tool_calls=tool_calls,
                        reasoning_tokens=[],
                        reasoning_content=None,
                        output=full_text,
                        finish_reason=finish_reason,
                        latency_ms=latency_ms,
                        token_usage=token_usage,
                        metadata={"adapter": "gemini", "model": self.model},
                        timestamp=datetime.now(),
                    ),
                    "full_text": full_text,
                    "latency_ms": latency_ms,
                },
            )

        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"Gemini stream failed: {e}") from e

    def _extract_tool_calls_from_text(self, text: str) -> list[ToolCall]:
        """Extract tool calls from accumulated text (best-effort for streaming)."""
        # In streaming mode we may not get structured tool calls,
        # so return empty list; tool calls are better captured in non-streaming mode.
        return []

    @classmethod
    def list_models(cls) -> list[str]:
        """List commonly used Gemini model ids and aliases."""
        return [
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "gemini-2.5-flash",
            "gemini-flash-lite-latest",
            "gemini-pro-latest",
        ]
