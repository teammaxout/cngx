"""cogscope submit — opt-in anonymous drift data for the public tracker."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

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


def _find_tracker_root(start: Optional[Path] = None) -> Path:
    """Locate tracker/ directory (repo root or COGSCOPE_TRACKER_PATH)."""
    import os

    env = os.getenv("COGSCOPE_TRACKER_PATH")
    if env:
        p = Path(env)
        if (p / "data").is_dir():
            return p
    cwd = start or Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        tracker = candidate / "tracker"
        if (tracker / "data").is_dir():
            return tracker
    return cwd / "tracker"


def build_submit_payload(
    fp,
    baseline_label: str,
    drift_score: float,
    record_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build an anonymized submission record from a fingerprint."""
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id or str(uuid.uuid4()),
        "timestamp": fp.timestamp.isoformat() + "Z"
        if fp.timestamp.tzinfo is None
        else fp.timestamp.isoformat(),
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
    from cogscope.diff.engine import DiffEngine
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

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


def _write_pending(tracker_root: Path, payload: dict[str, Any]) -> Path:
    pending = tracker_root / "data" / "community" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    out = pending / f"{payload['record_id']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return out


def _try_gh_pr(tracker_root: Path, payload: dict[str, Any], repo_root: Path) -> bool:
    """Create community JSON and open PR via gh CLI. Returns True on success."""
    if not shutil.which("gh"):
        return False
    community = tracker_root / "data" / "community"
    community.mkdir(parents=True, exist_ok=True)
    rel = f"tracker/data/community/{payload['record_id']}.json"
    out = repo_root / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")

    branch = f"submit/{payload['record_id'][:8]}"
    title = f"community: drift record {payload['model']} ({payload['record_id'][:8]})"
    body = (
        "Anonymous community drift submission via `cogscope submit`.\n\n"
        f"- Model: `{payload['model']}`\n"
        f"- Baseline label: `{payload['baseline_label']}`\n"
        f"- Drift score: `{payload['drift_score']}`\n"
        f"- Timestamp: `{payload['timestamp']}`\n\n"
        "No prompt or output text is included."
    )
    try:
        subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "add", rel], cwd=repo_root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", title],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        subprocess.run(["git", "checkout", "-"], cwd=repo_root, check=False, capture_output=True)
        if out.exists():
            out.unlink()
        return False


def run_submit(
    baseline: str,
    task_id: Optional[str] = None,
    limit: int = 5,
    yes: bool = False,
    dry_run: bool = False,
) -> int:
    """Preview, confirm, and submit anonymized drift records."""
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
            "[bold]Preview — exact payload(s) to submit[/]\n\n"
            "Contains ONLY model name, timestamp, numeric metrics, drift score, "
            "and your baseline label. [bold]No prompts or outputs.[/]",
            border_style="cyan",
        )
    )
    console.print(Syntax(text, "json", theme="monokai", line_numbers=False))

    if dry_run:
        console.print("[dim]Dry run — nothing sent.[/]")
        return 0

    if not yes:
        console.print()
        if not typer.confirm(
            f"Submit {len(payloads)} record(s) to the public tracker?",
            default=False,
        ):
            console.print("[yellow]Cancelled. Nothing was sent.[/]")
            return 0

    tracker_root = _find_tracker_root()
    repo_root = tracker_root.parent
    submitted = 0
    for payload in payloads:
        validate_submit_payload(payload)
        if _try_gh_pr(tracker_root, payload, repo_root):
            console.print(f"[green]OK[/] Opened PR for {payload['record_id']}")
            submitted += 1
        else:
            path = _write_pending(tracker_root, payload)
            console.print(
                Panel(
                    f"[green]OK[/] Wrote [cyan]{path}[/]\n\n"
                    "No GitHub CLI access — open a PR manually:\n"
                    f"  1. Copy to [cyan]tracker/data/community/{payload['record_id']}.json[/]\n"
                    "  2. git checkout -b submit/your-name\n"
                    "  3. git add tracker/data/community/\n"
                    "  4. git commit -m 'community: drift submission'\n"
                    "  5. git push && gh pr create",
                    title="Manual submission",
                    border_style="yellow",
                )
            )
            submitted += 1

    console.print(f"[bold]Done.[/] {submitted} record(s) prepared.")
    return 0
