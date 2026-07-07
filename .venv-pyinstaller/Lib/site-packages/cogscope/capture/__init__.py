"""Trace capture module for Cogscope."""

from cogscope.capture.adapters.base import BaseAdapter
from cogscope.capture.adapters.mock import MockAdapter
from cogscope.capture.tracer import CogscopeTracer


def __getattr__(name):
    """Lazy import optional adapters."""
    if name == "OpenAIAdapter":
        from cogscope.capture.adapters.openai import OpenAIAdapter

        return OpenAIAdapter
    if name == "GeminiAdapter":
        from cogscope.capture.adapters.gemini import GeminiAdapter

        return GeminiAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CogscopeTracer",
    "BaseAdapter",
    "OpenAIAdapter",
    "MockAdapter",
]
