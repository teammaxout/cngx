"""cngx submit, opt-in drift metrics for the community tracker."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from cngx.tracker_endpoints import submit_url

console = Console(stderr=True)

SCHEMA_VERSION = 1

# Privacy guarantee: only these keys may appear in a submission payload.
ALLOWED_SUBMIT_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "record_id",
        "timestamp",
        "model",
        "baseline_label",
        "drift_score",
        "depth",
        "verification_steps",
        "hedging_ratio",
        "branching_factor",
        "total_steps",
        "correction_count",
        "uncertainty_markers",
        "output_length",
        "reasoning_length",
    }
)

# Keys that must never appear (free-text / identifying content).
FORBIDDEN_SUBMIT_KEYS: frozenset[str] = frozenset(
    {
        "prompt",
        "output",
        "reasoning",
        "reasoning_content",
        "trace_id",
        "task_id",
        "messages",
        "content",
        "text",
        "description",
        "system_message",
        "user_message",
        "adapter_type",
        "metadata",
        "tool_call_sequence",
        "signature_hash",
    }
)

MAX_STRING_LEN = 128


def build_submit_payload(
    fp,
    baseline_label: str,
    drift_score: float,
    record_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a submission record from a fingerprint (allowlisted fields only)."""
    import uuid

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id or str(uuid.uuid4()),
        "timestamp": (
            fp.timestamp.isoformat() + "Z"
            if fp.timestamp.tzinfo is None
            else fp.timestamp.isoformat()
        ),
        "model": fp.model,
        "baseline_label": baseline_label,
        "drift_score": round(float(drift_score), 4),
        "depth": int(fp.depth),
        "verification_steps": int(fp.verification_steps),
        "hedging_ratio": round(float(fp.hedging_ratio), 4),
        "branching_factor": round(float(fp.branching_factor), 4),
        "total_steps": int(fp.total_steps),
        "correction_count": int(fp.correction_count),
        "uncertainty_markers": int(fp.uncertainty_markers),
        "output_length": int(fp.output_length),
        "reasoning_length": int(fp.reasoning_length),
    }


def validate_submit_payload(payload: dict[str, Any]) -> None:
    """Raise ValueError if payload violates the privacy schema."""
    keys = set(payload.keys())
    extra = keys - ALLOWED_SUBMIT_KEYS
    if extra:
        raise ValueError(f"Disallowed keys in payload: {sorted(extra)}")
    forbidden = keys & FORBIDDEN_SUBMIT_KEYS
    if forbidden:
        raise ValueError(f"Forbidden keys in payload: {sorted(forbidden)}")

    for key, value in payload.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            continue
        if isinstance(value, str):
            if len(value) > MAX_STRING_LEN:
                raise ValueError(f"String field {key} exceeds max length ({MAX_STRING_LEN})")
            continue
        raise ValueError(f"Field {key} has disallowed type {type(value).__name__}")

    serialized = json.dumps(payload).lower()
    for forbidden in FORBIDDEN_SUBMIT_KEYS:
        if f'"{forbidden}"' in serialized:
            raise ValueError(f"Forbidden key present in serialized payload: {forbidden}")


def collect_payloads(
    baseline: str,
    task_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Read local DB and build submission payloads."""
    from cngx.diff.engine import DiffEngine
    from cngx.storage.database import get_database
    from cngx.versioning.baseline import BaselineManager

    db = get_database()
    bm = BaselineManager(db)
    baseline_fp = bm.get_fingerprint(baseline)
    baseline_row = bm.get(baseline)

    if task_id:
        fingerprints = db.get_fingerprints_by_task(task_id, limit=limit)
    else:
        traces = db.get_recent_traces(limit=limit * 2)
        fingerprints = []
        for t in traces:
            fp = db.get_fingerprint_by_trace(t.id)
            if fp:
                fingerprints.append(fp)
            if len(fingerprints) >= limit:
                break

    engine = DiffEngine()
    payloads: list[dict[str, Any]] = []
    for fp in fingerprints:
        if fp.trace_id == baseline_row.trace_id:
            continue
        drift = engine.diff(baseline_fp, fp).drift_score
        payloads.append(build_submit_payload(fp, baseline, drift))
    return payloads


def post_submit_payload(
    payload: dict[str, Any],
    endpoint: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    """POST one validated record to the public tracker API. Returns record_id."""
    validate_submit_payload(payload)
    url = endpoint or submit_url()
    if "PLACEHOLDER" in url:
        raise RuntimeError(
            "Tracker submit endpoint is not configured. Set CNGX_SUBMIT_URL or update "
            "cngx/tracker_endpoints.py after deploying infra/."
        )

    owns_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        response = http.post(url, json=payload)
    finally:
        if owns_client:
            http.close()

    if response.status_code == 201:
        data = response.json()
        return str(data.get("record_id", payload["record_id"]))

    detail = response.text[:500]
    try:
        detail = response.json().get("error", detail)
    except Exception:
        pass
    raise RuntimeError(f"Submit failed ({response.status_code}): {detail}")


def run_submit(
    baseline: str,
    task_id: Optional[str] = None,
    limit: int = 5,
    yes: bool = False,
    dry_run: bool = False,
    endpoint: Optional[str] = None,
) -> int:
    """Preview, confirm, and submit opt-in drift records."""
    try:
        payloads = collect_payloads(baseline, task_id, limit)
    except Exception as e:
        console.print(f"[red]Could not collect fingerprints: {e}[/]")
        return 1

    if not payloads:
        console.print("[yellow]No fingerprints to submit for this baseline/task.[/]")
        return 1

    for p in payloads:
        validate_submit_payload(p)

    preview = payloads if len(payloads) == 1 else payloads
    text = json.dumps(preview, indent=2)
    console.print(
        Panel(
            "[bold]Preview, exact payload(s) to submit[/]\n\n"
            "Contains ONLY model name, timestamp, numeric metrics, drift score, "
            "and your baseline label. [bold]No prompts or outputs.[/]\n\n"
            "No personal identity is collected or stored. No GitHub account required.",
            border_style="cyan",
        )
    )
    console.print(Syntax(text, "json", theme="monokai", line_numbers=False))

    if dry_run:
        console.print("[dim]Dry run, nothing sent.[/]")
        return 0

    if not yes:
        console.print()
        if not typer.confirm(
            f"Submit {len(payloads)} record(s) to the public tracker?",
            default=False,
        ):
            console.print("[yellow]Cancelled. Nothing was sent.[/]")
            return 0

    submitted = 0
    with httpx.Client(timeout=30.0) as client:
        for payload in payloads:
            try:
                record_id = post_submit_payload(payload, endpoint=endpoint, client=client)
            except Exception as exc:
                console.print(f"[red]Submit failed for {payload['record_id']}: {exc}[/]")
                return 1
            console.print(f"[green]OK[/] Submitted {record_id}")
            submitted += 1

    console.print(
        f"[bold]Done.[/] {submitted} record(s) sent. " "Live tracker updates within a few minutes."
    )
    return 0
