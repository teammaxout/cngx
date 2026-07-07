"""Observability module, structured logging, Prometheus metrics, and tracing.

Production-grade observability for Cogscope:
- JSON structured logging with correlation IDs
- Prometheus metrics endpoint
- Request/enforcement instrumentation
"""

from cogscope.observability.logging import StructuredLogger, get_logger, setup_logging
from cogscope.observability.metrics import MetricsCollector, get_metrics

__all__ = [
    "setup_logging",
    "get_logger",
    "StructuredLogger",
    "MetricsCollector",
    "get_metrics",
]
