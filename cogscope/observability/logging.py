"""Structured JSON logging for Cogscope.

Replaces Python's default text logging with JSON-structured output
compatible with ELK Stack, Datadog, Splunk, and CloudWatch.

Features:
- JSON format with standard fields (timestamp, level, message, logger)
- Correlation ID propagation (per-request tracing)
- Sensitive data redaction (API keys, secrets)
- Configurable log levels per module
"""

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

# Thread-local storage for correlation IDs
_context = threading.local()


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID for the current thread/request."""
    cid = correlation_id or str(uuid.uuid4())[:12]
    _context.correlation_id = cid
    return cid


def get_correlation_id() -> str:
    """Get correlation ID for the current thread/request."""
    return getattr(_context, "correlation_id", "none")


# ---------------------------------------------------------------------------
# Sensitive data redaction
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    "api_key",
    "api-key",
    "apikey",
    "secret",
    "password",
    "token",
    "authorization",
    "key_hash",
]


def _redact_value(key: str, value: Any) -> Any:
    """Redact sensitive values based on key name."""
    if not isinstance(key, str):
        return value
    key_lower = key.lower()
    for pattern in _REDACT_PATTERNS:
        if pattern in key_lower:
            if isinstance(value, str) and len(value) > 8:
                return value[:4] + "****" + value[-4:]
            return "****"
    return value


def _redact_dict(data: dict) -> dict:
    """Recursively redact sensitive values in a dictionary."""
    redacted = {}
    for key, value in data.items():
        if isinstance(value, dict):
            redacted[key] = _redact_dict(value)
        else:
            redacted[key] = _redact_value(key, value)
    return redacted


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def __init__(self, service_name: str = "cogscope"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "correlation_id": get_correlation_id(),
        }

        # Add source location for errors
        if record.levelno >= logging.ERROR:
            log_entry["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
            }

        # Add extra fields (redacted)
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord("", 0, "", 0, "", (), None).__dict__ and key not in (
                "message",
                "args",
            ):
                extra_fields[key] = value

        if extra_fields:
            log_entry["extra"] = _redact_dict(extra_fields)

        return json.dumps(log_entry, default=str)


# ---------------------------------------------------------------------------
# Structured Logger wrapper
# ---------------------------------------------------------------------------


class StructuredLogger:
    """Convenience wrapper that adds structured context to log calls."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._logger.info(msg, extra=kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._logger.warning(msg, extra=kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._logger.error(msg, extra=kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._logger.debug(msg, extra=kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._logger.critical(msg, extra=kwargs)

    def enforcement(
        self,
        action: str,
        org_id: str,
        contract: str,
        model: str,
        passed: bool,
        **kwargs: Any,
    ) -> None:
        """Log an enforcement event with standard fields."""
        self._logger.info(
            f"Enforcement: {action}",
            extra={
                "event_type": "enforcement",
                "action": action,
                "org_id": org_id,
                "contract": contract,
                "model": model,
                "passed": passed,
                **kwargs,
            },
        )


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    service_name: str = "cogscope",
) -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_output: If True, use JSON format. If False, use human-readable format.
        service_name: Service name included in every log line.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if json_output:
        handler.setFormatter(JSONFormatter(service_name=service_name))
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ["urllib3", "httpcore", "httpx", "uvicorn.access"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger by name."""
    return StructuredLogger(name)
