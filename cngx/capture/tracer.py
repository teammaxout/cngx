"""Main tracer for cngx - the primary interface for capturing reasoning traces."""

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Optional, Type

from cngx.capture.adapters.base import BaseAdapter, StreamChunk
from cngx.capture.adapters.mock import MockAdapter
from cngx.core.config import CngxConfig, get_config
from cngx.core.exceptions import CaptureError
from cngx.core.models import BehavioralFingerprint, ReasoningTrace
from cngx.storage.database import Database, get_database


def _get_adapter_class(name: str) -> Type[BaseAdapter]:
    """Lazily resolve adapter class by name."""
    if name == "mock":
        return MockAdapter
    if name == "openai":
        from cngx.capture.adapters.openai import OpenAIAdapter

        return OpenAIAdapter
    if name == "gemini":
        from cngx.capture.adapters.gemini import GeminiAdapter

        return GeminiAdapter
    if name == "claude":
        from cngx.capture.adapters.claude import ClaudeAdapter

        return ClaudeAdapter
    raise CaptureError(f"Unknown adapter: {name}. Available: mock, openai, gemini, claude")


class CngxTracer:
    """Main tracer for capturing and storing reasoning traces.

    This is the primary interface for integrating cngx into your LLM pipeline.
    It wraps LLM calls, captures complete reasoning traces, and automatically
    generates behavioral fingerprints.

    Usage:
        tracer = CngxTracer(adapter="openai", model="gpt-4o")

        # Capture a trace
        trace = tracer.capture(
            task_id="math_reasoning",
            prompt="Solve: 2x + 5 = 13"
        )

        # Or use as a decorator
        @tracer.trace(task_id="code_gen")
        def generate_code(prompt: str) -> str:
            ...
    """

    ADAPTERS: dict[str, str] = {
        "openai": "openai",
        "mock": "mock",
        "gemini": "gemini",
        "claude": "claude",
    }

    def __init__(
        self,
        adapter: str = "openai",
        model: Optional[str] = None,
        config: Optional[CngxConfig] = None,
        db: Optional[Database] = None,
        auto_fingerprint: bool = True,
        **adapter_kwargs: Any,
    ):
        """Initialize the tracer.

        Args:
            adapter: Adapter type ("openai", "mock")
            model: Model name (defaults to config default)
            config: cngx configuration (defaults to global)
            db: Database instance (defaults to global)
            auto_fingerprint: Whether to automatically generate fingerprints
            **adapter_kwargs: Additional arguments for the adapter
        """
        self.config = config or get_config()

        # Set model
        if model is None:
            model = self.config.default_model

        # Initialize adapter
        if adapter not in self.ADAPTERS:
            raise CaptureError(
                f"Unknown adapter: {adapter}. Available: {list(self.ADAPTERS.keys())}"
            )

        adapter_cls = _get_adapter_class(adapter)
        self.adapter = adapter_cls(model=model, **adapter_kwargs)
        self.auto_fingerprint = auto_fingerprint

        # Initialize database
        self.db = db or get_database()

        # Lazy import to avoid circular deps
        self._fingerprint_extractor = None

    @property
    def fingerprint_extractor(self):
        """Lazy load fingerprint extractor."""
        if self._fingerprint_extractor is None:
            from cngx.fingerprint.extractor import FingerprintExtractor

            self._fingerprint_extractor = FingerprintExtractor()
        return self._fingerprint_extractor

    @staticmethod
    def ingest_output(
        output: str,
        *,
        prompt: str = "",
        task_id: str = "policy_check",
        model: str = "agent-output",
        reasoning_content: Optional[str] = None,
    ) -> tuple[ReasoningTrace, BehavioralFingerprint]:
        """Build a trace and fingerprint from existing agent output. No LLM calls."""
        from cngx.capture.trace_builder import build_trace_from_text
        from cngx.fingerprint.extractor import FingerprintExtractor

        trace = build_trace_from_text(
            prompt=prompt,
            output=output,
            task_id=task_id,
            model=model,
            reasoning_content=reasoning_content,
        )
        fingerprint = FingerprintExtractor().extract(trace)
        return trace, fingerprint

    def capture(
        self,
        prompt: str,
        task_id: str = "default",
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        save: bool = True,
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Capture a reasoning trace from an LLM call.

        This is the main method for capturing traces synchronously.

        Args:
            prompt: The user prompt
            task_id: Identifier for this task/use-case
            system_message: Optional system message
            tools: Optional tool definitions
            save: Whether to save to database
            **kwargs: Additional arguments for the adapter

        Returns:
            Complete reasoning trace
        """
        try:
            trace = self.adapter.call_sync(
                prompt=prompt,
                system_message=system_message,
                tools=tools,
                task_id=task_id,
                **kwargs,
            )

            if save:
                self._save_trace(trace)

            return trace
        except Exception as e:
            raise CaptureError(f"Failed to capture trace: {e}")

    async def capture_async(
        self,
        prompt: str,
        task_id: str = "default",
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        save: bool = True,
        **kwargs: Any,
    ) -> ReasoningTrace:
        """Capture a reasoning trace asynchronously.

        Args:
            prompt: The user prompt
            task_id: Identifier for this task/use-case
            system_message: Optional system message
            tools: Optional tool definitions
            save: Whether to save to database
            **kwargs: Additional arguments for the adapter

        Returns:
            Complete reasoning trace
        """
        try:
            trace = await self.adapter.call(
                prompt=prompt,
                system_message=system_message,
                tools=tools,
                task_id=task_id,
                **kwargs,
            )

            if save:
                self._save_trace(trace)

            return trace
        except Exception as e:
            raise CaptureError(f"Failed to capture trace: {e}")

    def capture_stream(
        self,
        prompt: str,
        task_id: str = "default",
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        save: bool = True,
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Capture a reasoning trace with synchronous streaming.

        Yields StreamChunk objects as tokens arrive. The final chunk
        (is_final=True) contains the complete ReasoningTrace in
        chunk.metadata["trace"].

        Args:
            prompt: The user prompt
            task_id: Identifier for this task/use-case
            system_message: Optional system message
            tools: Optional tool definitions
            save: Whether to save the final trace to database
            **kwargs: Additional arguments for the adapter

        Yields:
            StreamChunk objects with partial text and final trace
        """
        try:
            final_trace = None
            for chunk in self.adapter.call_stream_sync(
                prompt=prompt,
                system_message=system_message,
                tools=tools,
                task_id=task_id,
                **kwargs,
            ):
                if chunk.is_final and chunk.metadata and "trace" in chunk.metadata:
                    final_trace = chunk.metadata["trace"]
                    if save and final_trace:
                        self._save_trace(final_trace)
                yield chunk
        except CaptureError:
            raise
        except Exception as e:
            raise CaptureError(f"Failed to capture stream: {e}")

    async def capture_stream_async(
        self,
        prompt: str,
        task_id: str = "default",
        system_message: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        save: bool = True,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Capture a reasoning trace with async streaming.

        Yields StreamChunk objects as tokens arrive. The final chunk
        (is_final=True) contains the complete ReasoningTrace in
        chunk.metadata["trace"].

        Args:
            prompt: The user prompt
            task_id: Identifier for this task/use-case
            system_message: Optional system message
            tools: Optional tool definitions
            save: Whether to save the final trace to database
            **kwargs: Additional arguments for the adapter

        Yields:
            StreamChunk objects with partial text and final trace
        """
        try:
            final_trace = None
            async for chunk in self.adapter.call_stream(
                prompt=prompt,
                system_message=system_message,
                tools=tools,
                task_id=task_id,
                **kwargs,
            ):
                if chunk.is_final and chunk.metadata and "trace" in chunk.metadata:
                    final_trace = chunk.metadata["trace"]
                    if save and final_trace:
                        self._save_trace(final_trace)
                yield chunk
        except CaptureError:
            raise
        except Exception as e:
            raise CaptureError(f"Failed to capture stream: {e}")

    def _save_trace(self, trace: ReasoningTrace) -> None:
        """Save trace and optionally generate fingerprint."""
        # Save trace
        self.db.save_trace(trace)

        # Generate and save fingerprint
        if self.auto_fingerprint:
            fingerprint = self.fingerprint_extractor.extract(trace)
            self.db.save_fingerprint(fingerprint)

    def get_trace(self, trace_id: str) -> ReasoningTrace:
        """Get a trace by ID."""
        return self.db.get_trace(trace_id)

    def get_traces(self, task_id: str, limit: int = 100) -> list[ReasoningTrace]:
        """Get traces for a task."""
        return self.db.get_traces_by_task(task_id, limit=limit)

    def get_fingerprint(self, trace_id: str) -> Optional[BehavioralFingerprint]:
        """Get fingerprint for a trace."""
        return self.db.get_fingerprint_by_trace(trace_id)

    def update_adapter_config(self, **kwargs: Any) -> None:
        """Update the adapter configuration.

        Use this to change model parameters like temperature, top_p, etc.
        Changes will affect subsequent captures.
        """
        self.adapter.update_config(**kwargs)

    def switch_model(self, model: str) -> None:
        """Switch to a different model."""
        self.adapter.model = model

    def switch_adapter(self, adapter: str, **kwargs: Any) -> None:
        """Switch to a different adapter."""
        if adapter not in self.ADAPTERS:
            raise CaptureError(f"Unknown adapter: {adapter}")

        model = kwargs.pop("model", self.adapter.model)
        adapter_cls = _get_adapter_class(adapter)
        self.adapter = adapter_cls(model=model, **kwargs)


def create_tracer(
    adapter: str = "openai",
    model: Optional[str] = None,
    **kwargs: Any,
) -> CngxTracer:
    """Convenience function to create a tracer.

    Args:
        adapter: Adapter type
        model: Model name
        **kwargs: Additional arguments

    Returns:
        Configured CngxTracer instance
    """
    return CngxTracer(adapter=adapter, model=model, **kwargs)
