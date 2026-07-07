"""Post-request capture, fingerprinting, and drift analysis."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from cogscope.core.models import ModelConfig, ReasoningTrace, TokenUsage
from cogscope.drift.detector import DriftDetector
from cogscope.drift.semantic import get_semantic_analyzer
from cogscope.drift.trajectory import detect_verification_collapse, verification_health_label
from cogscope.fingerprint.extractor import FingerprintExtractor
from cogscope.observability.otel import emit_capture_span, is_otel_enabled
from cogscope.proxy.events import CaptureEvent, get_event_bus
from cogscope.storage.database import get_database

logger = logging.getLogger("cogscope.proxy.analysis")

_semantic_enabled: bool = False


def set_semantic_analysis_enabled(enabled: bool) -> None:
    """Enable optional local embedding drift (requires cogscope[semantic])."""
    global _semantic_enabled
    _semantic_enabled = enabled


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
    session_id: str,
    session_turn: int,
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
        system_message=next(
            (m.get("content") for m in messages if m.get("role") == "system"), None
        ),
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
        metadata={"source": "proxy", "session_id": session_id, "session_turn": session_turn},
    )


def _find_pinned_baseline(task_id: str, model: str):
    db = get_database()
    baselines = db.get_baselines_for_task(task_id)
    active = [b for b in baselines if b.is_active]
    if not active:
        return None, None
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


def _publish_capture_event(
    *,
    trace: ReasoningTrace,
    fp,
    task_id: str,
    session_id: str,
    session_turn: int,
    session_turn_count: int,
    session_health: str,
    trajectory,
    assessment=None,
    no_baseline: bool = False,
) -> None:
    bus = get_event_bus()
    alert = False
    alert_msg = None
    metric_shifts: list[dict] = []

    if trajectory.collapse_detected:
        alert = True
        alert_msg = trajectory.summary

    if assessment is not None:
        if assessment.should_alert:
            alert = True
            parts = [alert_msg, "; ".join(assessment.plain_language) or assessment.summary]
            alert_msg = "; ".join(p for p in parts if p)
        metric_shifts = assessment.outliers

    bus.publish(
        CaptureEvent(
            timestamp=datetime.utcnow(),
            trace_id=trace.id,
            model=trace.model,
            task_id=task_id,
            depth=fp.depth,
            verification_steps=fp.verification_steps,
            hedging_ratio=fp.hedging_ratio,
            drift_score=None if assessment is None else assessment.drift_score,
            baseline_name=None if assessment is None else assessment.baseline_name,
            alert=alert,
            alert_message=alert_msg,
            metric_shifts=metric_shifts,
            no_baseline=no_baseline,
            session_id=session_id,
            session_turn=session_turn,
            session_turn_count=session_turn_count,
            session_health=session_health,
            session_stability_warning=trajectory.collapse_detected,
            session_warning_message=trajectory.summary if trajectory.collapse_detected else None,
        )
    )


async def analyze_completed_call(
    provider: str,
    request_body: dict,
    response_bytes: bytes,
    task_id: str,
    latency_ms: float,
    was_stream: bool = False,
    session_id: str = "default",
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

        db = get_database()
        session_turn = db.allocate_session_turn(session_id)

        trace = _build_trace_from_openai(
            request_body, response_body, task_id, latency_ms, session_id, session_turn
        )
        extractor = FingerprintExtractor()
        fp = extractor.extract(trace)
        fp.metadata["session_id"] = session_id
        fp.metadata["session_turn"] = session_turn

        db.save_trace(trace)
        db.save_fingerprint(fp, session_id=session_id, session_turn=session_turn)

        session_fps = db.get_fingerprints_by_session(session_id)
        verification_series = [f.verification_steps for f in session_fps]
        correction_series = [f.correction_count for f in session_fps]
        trajectory = detect_verification_collapse(verification_series, correction_series)
        session_health = verification_health_label(verification_series)
        session_turn_count = len(session_fps)

        baseline, baseline_fp = _find_pinned_baseline(task_id, trace.model)

        if baseline_fp is None:
            _publish_capture_event(
                trace=trace,
                fp=fp,
                task_id=task_id,
                session_id=session_id,
                session_turn=session_turn,
                session_turn_count=session_turn_count,
                session_health=session_health,
                trajectory=trajectory,
                no_baseline=True,
            )
            return

        historical = db.get_fingerprints_by_task(task_id, limit=30)
        detector = DriftDetector(db=db)
        semantic_analyzer = get_semantic_analyzer(_semantic_enabled)
        if semantic_analyzer is not None and historical:
            trace_outputs = {}
            for hfp in historical:
                try:
                    ht = db.get_trace(hfp.trace_id)
                    if ht:
                        trace_outputs[hfp.trace_id] = ht.output or ""
                except Exception:
                    pass
            if not semantic_analyzer._baseline_embeddings:
                semantic_analyzer.seed_from_fingerprints(historical, trace_outputs)

        assessment = detector.assess_against_pinned_baseline(
            fp,
            baseline_fp,
            historical,
            baseline_name=baseline.name if baseline else None,
            model_name=trace.model,
            semantic_text=trace.output if _semantic_enabled else None,
            semantic_analyzer=semantic_analyzer,
        )

        if is_otel_enabled():
            emit_capture_span(
                trace=trace,
                fingerprint=fp,
                provider=provider,
                drift_score=assessment.drift_score,
                structural_drift=assessment.structural_alert,
                semantic_drift=assessment.semantic_alert,
                baseline_name=baseline.name if baseline else None,
            )

        _publish_capture_event(
            trace=trace,
            fp=fp,
            task_id=task_id,
            session_id=session_id,
            session_turn=session_turn,
            session_turn_count=session_turn_count,
            session_health=session_health,
            trajectory=trajectory,
            assessment=assessment,
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
    session_id: str = "default",
) -> None:
    """Fire-and-forget analysis so streaming is never blocked."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            analyze_completed_call(
                provider,
                request_body,
                response_bytes,
                task_id,
                latency_ms,
                was_stream,
                session_id,
            )
        )
    except RuntimeError:
        asyncio.run(
            analyze_completed_call(
                provider,
                request_body,
                response_bytes,
                task_id,
                latency_ms,
                was_stream,
                session_id,
            )
        )
