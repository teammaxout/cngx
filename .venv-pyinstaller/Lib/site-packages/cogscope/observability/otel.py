"""OpenTelemetry GenAI semantic conventions and optional OTLP export.

Constructs OTel-compliant spans for proxied LLM calls with Cogscope fingerprint
attributes under the cogscope.fingerprint.* namespace. Export is optional and
off by default; local DuckDB storage remains the default path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from cogscope.core.models import BehavioralFingerprint, ReasoningTrace

logger = logging.getLogger("cogscope.observability.otel")

_otel_enabled = False
_otel_endpoint = "http://localhost:4318"
_tracer: Any = None
_provider: Any = None

# GenAI semantic convention attribute keys (OpenTelemetry / OpenLLMetry)
ATTR_GENAI_SYSTEM = "gen_ai.system"
ATTR_GENAI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GENAI_RESPONSE_ID = "gen_ai.response.id"
ATTR_GENAI_OPERATION = "gen_ai.operation.name"

COGSCOPE_FP_PREFIX = "cogscope.fingerprint"


def configure_otel(
    *,
    enabled: bool,
    endpoint: str = "http://localhost:4318",
    service_name: str = "cogscope-proxy",
) -> None:
    """Enable or disable OTLP HTTP export (requires cogscope[otel] extra)."""
    global _otel_enabled, _otel_endpoint, _tracer, _provider

    _otel_enabled = enabled
    _otel_endpoint = endpoint.rstrip("/")

    if not enabled:
        if _provider is not None:
            try:
                _provider.shutdown()
            except Exception:
                pass
        _tracer = None
        _provider = None
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise ImportError("OpenTelemetry export requires: pip install cogscope[otel]") from exc

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{_otel_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider = provider
    _tracer = trace.get_tracer("cogscope.proxy")


def is_otel_enabled() -> bool:
    return _otel_enabled


def _fingerprint_attributes(fp: BehavioralFingerprint) -> dict[str, Any]:
    return {
        f"{COGSCOPE_FP_PREFIX}.depth": fp.depth,
        f"{COGSCOPE_FP_PREFIX}.total_steps": fp.total_steps,
        f"{COGSCOPE_FP_PREFIX}.verification_steps": fp.verification_steps,
        f"{COGSCOPE_FP_PREFIX}.hedging_ratio": fp.hedging_ratio,
        f"{COGSCOPE_FP_PREFIX}.correction_count": fp.correction_count,
        f"{COGSCOPE_FP_PREFIX}.branching_factor": fp.branching_factor,
        f"{COGSCOPE_FP_PREFIX}.uncertainty_markers": fp.uncertainty_markers,
        f"{COGSCOPE_FP_PREFIX}.output_length": fp.output_length,
    }


def emit_capture_span(
    *,
    trace: ReasoningTrace,
    fingerprint: BehavioralFingerprint,
    provider: str,
    drift_score: Optional[float] = None,
    structural_drift: bool = False,
    semantic_drift: bool = False,
    baseline_name: Optional[str] = None,
) -> None:
    """Record an OTel span for a completed proxied capture."""
    if not _otel_enabled or _tracer is None:
        return

    attrs: dict[str, Any] = {
        ATTR_GENAI_SYSTEM: provider,
        ATTR_GENAI_REQUEST_MODEL: trace.model,
        ATTR_GENAI_RESPONSE_ID: trace.id,
        ATTR_GENAI_OPERATION: "chat",
        "cogscope.task_id": trace.task_id,
        "cogscope.latency_ms": trace.latency_ms,
        "cogscope.structural_drift": structural_drift,
        "cogscope.semantic_drift": semantic_drift,
    }
    if baseline_name:
        attrs["cogscope.baseline_name"] = baseline_name
    if drift_score is not None:
        attrs["cogscope.drift_score"] = drift_score
    attrs.update(_fingerprint_attributes(fingerprint))

    try:
        with _tracer.start_as_current_span("gen_ai.chat") as span:
            span.set_attributes(attrs)
            span.set_attribute("cogscope.captured_at", datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        logger.debug("OTel span export failed: %s", exc)
