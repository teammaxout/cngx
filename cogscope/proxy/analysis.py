"""Post-request capture, fingerprinting, and drift analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage
from cogscope.drift.detector import DriftDetector
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.proxy.events import CaptureEvent, get_event_bus
from cogscope.storage.database import get_database
from cogscope.versioning.baseline import BaselineManager

logger = logging.getLogger("cogscope.proxy.analysis")


def _extract_prompt(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                return "\n".join(parts)
            return str(content)
    return ""


def _build_trace_from_openai(
    request_body: dict,
    response_body: dict,
    task_id: str,
    latency_ms: float,
) -> ReasoningTrace:
    model = request_body.get("model", "unknown")
    messages = request_body.get("messages", [])
    prompt = _extract_prompt(messages)

    choice = (response_body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    output = message.get("content") or ""
    reasoning = message.get("reasoning_content")

    usage = response_body.get("usage") or {}
    token_usage = TokenUsage(
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )

    return ReasoningTrace(
        id=f"trace_{uuid.uuid4().hex[:12]}",
        timestamp=datetime.utcnow(),
        task_id=task_id,
        model=model,
        adapter_type="openai",
        system_message=next((m.get("content") for m in messages if m.get("role") == "system"), None),
        prompt=prompt,
        messages=messages,
        output=output,
        reasoning_content=reasoning,
        token_usage=token_usage,
        latency_ms=latency_ms,
        model_config_params=ModelConfig(
            temperature=request_body.get("temperature", 1.0),
            max_tokens=request_body.get("max_tokens"),
        ),
        metadata={"source": "proxy"},
    )


def _find_pinned_baseline(task_id: str, model: str):
    db = get_database()
    baselines = db.get_baselines_for_task(task_id)
    active = [b for b in baselines if b.is_active]
    if not active:
        return None, None
    # Prefer most recent active baseline for this task
    baseline = sorted(active, key=lambda b: b.created_at, reverse=True)[0]
    try:
        fp = db.get_fingerprint(baseline.fingerprint_id)
        if fp is None:
            fp = db.get_fingerprint_by_trace(baseline.trace_id)
        return baseline, fp
    except Exception:
        return baseline, None


def _parse_openai_response(response_bytes: bytes, was_stream: bool) -> dict | None:
    if not response_bytes.strip():
        return None
    text = response_bytes.decode("utf-8", errors="replace")
    if was_stream or text.startswith("data:"):
        content = ""
        for line in text.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                chunk = json.loads(payload)
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                if delta.get("content"):
                    content += delta["content"]
            except json.JSONDecodeError:
                continue
        return {"choices": [{"message": {"content": content}}], "usage": {}}
    try:
        return json.loads(response_bytes)
    except json.JSONDecodeError:
        return None


async def analyze_completed_call(
    provider: str,
    request_body: dict,
    response_bytes: bytes,
    task_id: str,
    latency_ms: float,
    was_stream: bool = False,
) -> None:
    """Capture fingerprint and optional drift check (runs off hot path)."""
    try:
        if provider != "openai":
            return

        if not response_bytes.strip():
            return

        response_body = _parse_openai_response(response_bytes, was_stream)
        if response_body is None:
            return

        trace = _build_trace_from_openai(request_body, response_body, task_id, latency_ms)
        extractor = FingerprintExtractor()
        fp = extractor.extract(trace)

        db = get_database()
        db.save_trace(trace)
        db.save_fingerprint(fp)

        baseline, baseline_fp = _find_pinned_baseline(task_id, trace.model)
        bus = get_event_bus()

        if baseline_fp is None:
            bus.publish(
                CaptureEvent(
                    timestamp=datetime.utcnow(),
                    trace_id=trace.id,
                    model=trace.model,
                    task_id=task_id,
                    depth=fp.depth,
                    verification_steps=fp.verification_steps,
                    hedging_ratio=fp.hedging_ratio,
                    no_baseline=True,
                    alert_message="No baseline pinned — captured and fingerprinted only.",
                )
            )
            return

        historical = db.get_fingerprints_by_task(task_id, limit=30)
        detector = DriftDetector(db=db)
        assessment = detector.assess_against_pinned_baseline(
            fp,
            baseline_fp,
            historical,
            baseline_name=baseline.name if baseline else None,
            model_name=trace.model,
        )

        alert_msg = None
        if assessment.should_alert:
            alert_msg = "; ".join(assessment.plain_language) or assessment.summary

        bus.publish(
            CaptureEvent(
                timestamp=datetime.utcnow(),
                trace_id=trace.id,
                model=trace.model,
                task_id=task_id,
                depth=fp.depth,
                verification_steps=fp.verification_steps,
                hedging_ratio=fp.hedging_ratio,
                drift_score=assessment.drift_score,
                baseline_name=baseline.name if baseline else None,
                alert=assessment.should_alert,
                alert_message=alert_msg,
                metric_shifts=assessment.outliers,
            )
        )
    except Exception as exc:
        logger.debug("Post-capture analysis failed: %s", exc, exc_info=True)


def schedule_analysis(
    provider: str,
    request_body: dict,
    response_bytes: bytes,
    task_id: str,
    latency_ms: float,
    was_stream: bool = False,
) -> None:
    """Fire-and-forget analysis so streaming is never blocked."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            analyze_completed_call(
                provider, request_body, response_bytes, task_id, latency_ms, was_stream
            )
        )
    except RuntimeError:
        asyncio.run(
            analyze_completed_call(
                provider, request_body, response_bytes, task_id, latency_ms, was_stream
            )
        )
