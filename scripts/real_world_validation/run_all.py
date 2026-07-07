#!/usr/bin/env python3
"""Real-world validation runner for Cogscope pre-launch checks.

Requires OPENAI_API_KEY in the environment. Never logs or writes key material.
Optional: ANTHROPIC_API_KEY, GOOGLE_API_KEY for multi-provider smoke tests.

Usage (from scratch directory after cogscope init --yes):
    python path/to/run_all.py --scratch /path/to/scratch --results /path/to/results.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Repo root for imports when run as script
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


TASK1_PROMPTS = [
    {
        "id": "reasoning_multi_step",
        "prompt": (
            "A train leaves Station A at 9:00 traveling 60 mph. Another leaves Station B "
            "at 10:00 traveling 80 mph toward A on the same track, 280 miles apart. "
            "When do they meet? Show each step and verify your arithmetic."
        ),
    },
    {
        "id": "coding_small",
        "prompt": (
            "Write a Python function `is_palindrome(s: str) -> bool` that ignores spaces "
            "and case. Include two assert examples in your answer."
        ),
    },
    {
        "id": "verification_invite",
        "prompt": (
            "Estimate how many golf balls fit in a school bus. State assumptions, "
            "calculate, then explicitly verify one assumption with a sanity check."
        ),
    },
    {
        "id": "debug_reasoning",
        "prompt": (
            "Find the bug: `def avg(nums): return sum(nums) / len(nums) - 1`. "
            "Explain why it is wrong and give the corrected function."
        ),
    },
    {
        "id": "structured_steps",
        "prompt": (
            "List exactly 5 steps to harden a minimal REST API. Number each step. "
            "End with one sentence on how you would verify step 3."
        ),
    },
    {
        "id": "factual_lookup",
        "prompt": (
            "What is the time complexity of merge sort? Give Big-O, one sentence why, "
            "and double-check with a 4-element example."
        ),
    },
]

TASK5_PROMPTS = [
    "Design a rate limiter for an API gateway. Outline data structures and tradeoffs.",
    "Refactor this logic in words: nested if/else password reset flow with email token expiry.",
    "Explain CAP theorem with a concrete outage scenario for a chat app.",
    "Write pseudocode for a worker queue with retries and dead-letter handling.",
    "Compare SQLite vs Postgres for a local-first sync app with 3 bullet tradeoffs.",
    "Debug scenario: p99 latency spikes only on Tuesdays. List 6 hypotheses ranked.",
    "Specify tests for a function that parses ISO-8601 durations.",
    "Describe how to detect duplicate webhook deliveries idempotently.",
]

SESSION_FOLLOWUPS = [
    "Good start. Add input validation for empty strings and None.",
    "Add type hints and a one-line docstring.",
    "Write a second test case for non-palindrome with spaces.",
    "Handle Unicode characters; mention normalization briefly.",
    "Refactor to avoid allocating a reversed copy of the string.",
    "Add a benchmark note: time complexity of your approach.",
    "There is a bug when s has only spaces. Fix it.",
    "Add logging at debug level on empty input.",
    "Can you return False for non-str inputs instead of raising?",
    "Add a __main__ block with argparse for CLI usage.",
    "Support an optional case_sensitive flag defaulting to False.",
    "Document edge cases in a short comment block.",
    "Add a property-based test idea (no library needed).",
    "Optimize for early exit on length mismatch.",
    "Split into private helper _normalize(s).",
    "Add an example with punctuation like 'A man, a plan, a canal: Panama'.",
    "Review your last version for off-by-one in index loops.",
    "Summarize changes made across this session in 3 bullets.",
    "Any remaining security concerns for user-supplied strings?",
    "Final pass: simplify without changing behavior.",
    "Double-check all tests you mentioned still pass conceptually.",
    "Would your solution handle surrogate pairs? Brief yes/no with reason.",
    "Add complexity and memory notes in comments.",
    "Produce the final function only, no prose.",
    "Verify: does your final code still ignore spaces and case?",
]


def _require_openai() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")


def _start_proxy(
    session_id: Optional[str] = None,
    semantic: bool = False,
    otel: bool = False,
    otel_endpoint: str = "http://127.0.0.1:4318",
    port: int = 8642,
) -> threading.Thread:
    from cogscope.cli.wrap import ensure_proxy_running
    from cogscope.observability.otel import configure_otel
    from cogscope.proxy.analysis import set_semantic_analysis_enabled

    set_semantic_analysis_enabled(semantic)
    if otel:
        configure_otel(enabled=True, endpoint=otel_endpoint)
    return ensure_proxy_running(port=port, session_id=session_id) or threading.Thread()


def _openai_via_proxy(model: str, prompt: str, port: int = 8642) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=f"http://127.0.0.1:{port}/v1",
    )
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    elapsed = time.time() - t0
    text = resp.choices[0].message.content or ""
    return {
        "model": model,
        "latency_s": round(elapsed, 2),
        "output_chars": len(text),
        "output_preview": text[:200],
    }


def _fingerprints_summary(db, task_prefix: Optional[str] = None) -> list[dict[str, Any]]:
    rows = []
    for t in db.get_recent_traces(limit=50):
        if task_prefix and not t.task_id.startswith(task_prefix):
            continue
        fp = db.get_fingerprint_by_trace(t.id)
        if not fp:
            continue
        rows.append(
            {
                "trace_id": t.id,
                "task_id": t.task_id,
                "model": fp.model,
                "depth": fp.depth,
                "verification_steps": fp.verification_steps,
                "hedging_ratio": fp.hedging_ratio,
                "total_steps": fp.total_steps,
                "output_length": fp.output_length,
            }
        )
    return rows


def task1_smoke(scratch: Path, port: int = 8642) -> dict[str, Any]:
    _require_openai()
    os.chdir(scratch)
    _start_proxy(port=port)
    time.sleep(0.5)
    results = []
    for item in TASK1_PROMPTS:
        meta = _openai_via_proxy("gpt-4o-mini", item["prompt"], port=port)
        meta["prompt_id"] = item["id"]
        results.append(meta)
        time.sleep(0.3)

    from cogscope.storage.database import get_database

    db = get_database()
    fps = _fingerprints_summary(db)
    depths = {r["depth"] for r in fps}
    verifies = {r["verification_steps"] for r in fps}
    return {
        "provider": "openai",
        "path": "wrap/proxy",
        "calls": results,
        "fingerprints": fps[:12],
        "depth_unique": len(depths),
        "verification_unique": len(verifies),
        "non_degenerate": len(depths) > 1 or max(depths or {0}) > 0,
    }


def task1_direct_adapter(adapter: str, model: str) -> dict[str, Any]:
    from cogscope.capture.tracer import CogscopeTracer

    tracer = CogscopeTracer(adapter=adapter, model=model)
    results = []
    for item in TASK1_PROMPTS[:3]:
        trace = tracer.capture(prompt=item["prompt"], task_id=f"direct_{adapter}_{item['id']}", save=True)
        fp = tracer.get_fingerprint(trace.id)
        results.append(
            {
                "prompt_id": item["id"],
                "trace_id": trace.id,
                "depth": fp.depth if fp else None,
                "verification_steps": fp.verification_steps if fp else None,
            }
        )
    return {"adapter": adapter, "model": model, "results": results}


def task2_session(scratch: Path, port: int = 8642) -> dict[str, Any]:
    _require_openai()
    os.chdir(scratch)
    session_id = "real-session-1"
    _start_proxy(session_id=session_id, port=port)
    time.sleep(0.5)

    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=f"http://127.0.0.1:{port}/v1",
    )
    messages = [
        {
            "role": "user",
            "content": (
                "We are pair-programming. Write a Python function is_palindrome(s) "
                "ignoring spaces and case. Keep answers concise."
            ),
        }
    ]
    turns = []
    for i, followup in enumerate(SESSION_FOLLOWUPS, start=1):
        if i > 1:
            messages.append({"role": "user", "content": followup})
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
        )
        content = resp.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": content})
        turns.append({"turn": i, "chars": len(content)})
        time.sleep(0.25)

    from cogscope.storage.database import get_database

    db = get_database()
    fps = db.get_fingerprints_by_session(session_id)
    return {
        "session_id": session_id,
        "turns_run": len(turns),
        "fingerprints_in_session": len(fps),
        "verification_steps": [fp.verification_steps for fp in fps],
        "depths": [fp.depth for fp in fps],
    }


def task3_regression(scratch: Path, repo: Path) -> dict[str, Any]:
    _require_openai()
    os.chdir(scratch)
    suite = repo / "examples" / "regression_suite_real.yaml"
    policy = repo / "examples" / "contracts" / "basic_reasoning.yaml"
    baseline_out = scratch / ".baseline_outcomes.json"

    from cogscope.cli.regression_cmd import run_regression_suite

    # Run 1: seed baseline
    run_regression_suite(
        suite_path=suite,
        policy=policy,
        model="gpt-4o-mini",
        adapter="openai",
        baseline_outcomes_path=None,
        json_output=False,
    )

    # Capture baseline outcomes manually via tracer (run_regression_suite seeds on first run without comparison)
    from cogscope.capture.tracer import CogscopeTracer
    from cogscope.cli.check_cmd import _load_policy
    from cogscope.contracts import DeploymentGate
    from cogscope.drift.paired import evaluate_item_correctness, mcnemar_test
    import yaml

    with open(suite, encoding="utf-8") as f:
        items = yaml.safe_load(f)["items"]
    behavior_policy = _load_policy(policy)
    tracer = CogscopeTracer(adapter="openai", model="gpt-4o-mini")
    gate = DeploymentGate()

    def run_once() -> list[bool]:
        correct = []
        for i, item in enumerate(items):
            trace = tracer.capture(prompt=item["prompt"], task_id=f"regression_{i}", save=True)
            fp = tracer.get_fingerprint(trace.id)
            result = gate.check(fp, behavior_policy, trace)
            correct.append(
                evaluate_item_correctness(
                    trace.output or "",
                    expected_substrings=item.get("expected_substrings"),
                    forbidden_substrings=item.get("forbidden_substrings"),
                    policy_passed=result.passed and not result.blocked,
                )
            )
            time.sleep(0.2)
        return correct

    baseline_correct = run_once()
    time.sleep(3)
    current_correct = run_once()
    mcnemar = mcnemar_test(baseline_correct, current_correct)
    baseline_out.write_text(json.dumps({"correct": baseline_correct}, indent=2), encoding="utf-8")

    return {
        "n_items": len(items),
        "baseline_pass": sum(baseline_correct),
        "current_pass": sum(current_correct),
        "baseline_correct": baseline_correct,
        "current_correct": current_correct,
        "mcnemar_p": mcnemar.p_value,
        "shift_detected": mcnemar.shift_detected,
        "summary": mcnemar.summary,
    }


def task4_semantic(scratch: Path, port: int = 8643) -> dict[str, Any]:
    _require_openai()
    os.chdir(scratch)
    _start_proxy(semantic=True, port=port)
    time.sleep(1.0)
    out = _openai_via_proxy(
        "gpt-4o-mini",
        "Explain recursion with a factorial example. Use at least two verification phrases.",
        port=port,
    )
    return {"semantic_enabled": True, "call": out}


def task4_otel(scratch: Path, port: int = 8644) -> dict[str, Any]:
    """Start minimal OTLP HTTP receiver and one proxied call with --otel."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            received.append({"path": self.path, "bytes": len(body)})
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 4318), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    os.chdir(scratch)
    _start_proxy(otel=True, otel_endpoint="http://127.0.0.1:4318", port=port)
    time.sleep(0.5)
    _openai_via_proxy("gpt-4o-mini", "Say hello in one short sentence.", port=port)
    time.sleep(2.0)
    server.shutdown()
    return {"otel_live": len(received) > 0, "requests": received}


def task5_cross_model(scratch: Path) -> dict[str, Any]:
    _require_openai()
    os.chdir(scratch)
    from cogscope.capture.tracer import CogscopeTracer
    from cogscope.diff.engine import DiffEngine
    from cogscope.storage.database import get_database
    from cogscope.versioning.pinning import PinningManager

    strong = CogscopeTracer(adapter="openai", model="gpt-4o")
    weak = CogscopeTracer(adapter="openai", model="gpt-4o-mini")
    engine = DiffEngine()
    diffs = []
    last_strong_trace = None
    for i, prompt in enumerate(TASK5_PROMPTS):
        t_strong = strong.capture(prompt=prompt, task_id=f"cross_strong_{i}", save=True)
        last_strong_trace = t_strong
        fp_s = strong.get_fingerprint(t_strong.id)
        t_weak = weak.capture(prompt=prompt, task_id=f"cross_weak_{i}", save=True)
        fp_w = weak.get_fingerprint(t_weak.id)
        if fp_s and fp_w:
            d = engine.diff(fp_s, fp_w)
            diffs.append(
                {
                    "prompt_index": i,
                    "drift_score": round(d.drift_score, 4),
                    "significance": str(d.significance),
                }
            )
        time.sleep(0.3)

    from cogscope.versioning.baseline import BaselineManager

    db = get_database()
    pm = PinningManager(db)
    bm = BaselineManager(db)
    baseline = pm.pin(trace_id=last_strong_trace.id, name="cross_model_strong_baseline")

    from cogscope.drift.detector import DriftDetector

    detector = DriftDetector(db=db)
    baseline_fp = bm.get_fingerprint(baseline.name)
    alerts = []
    for i in range(len(TASK5_PROMPTS)):
        traces = db.get_recent_traces(limit=200)
        weak_traces = [t for t in traces if t.task_id == f"cross_weak_{i}"]
        if not weak_traces:
            continue
        fp_w = db.get_fingerprint_by_trace(weak_traces[0].id)
        if fp_w:
            assessment = detector.assess_against_pinned_baseline(
                fp_w, baseline_fp, [baseline_fp], baseline_name=baseline.name, model_name=fp_w.model
            )
            alerts.append(
                {
                    "i": i,
                    "drift_score": assessment.drift_score,
                    "should_alert": assessment.should_alert,
                }
            )

    drift_scores = [d["drift_score"] for d in diffs]
    return {
        "note": "INTERNAL ONLY, not for public tracker submission",
        "strong_model": "gpt-4o",
        "weak_model": "gpt-4o-mini",
        "per_pair_diffs": diffs,
        "mean_drift_score": round(sum(drift_scores) / len(drift_scores), 4) if drift_scores else 0,
        "max_drift_score": max(drift_scores) if drift_scores else 0,
        "any_alert": any(a["should_alert"] for a in alerts),
        "alerts": alerts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--task", choices=["all", "1", "2", "3", "4", "5"], default="all")
    args = parser.parse_args()

    args.scratch.mkdir(parents=True, exist_ok=True)
    os.chdir(args.scratch)
    if not (args.scratch / ".cogscope").exists():
        subprocess.run(["cogscope", "init", "--yes"], check=True, cwd=args.scratch)

    report: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "keys": {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "google": bool(os.getenv("GOOGLE_API_KEY")),
        },
    }

    if args.task in ("all", "1"):
        report["task1_openai_proxy"] = task1_smoke(args.scratch)
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                report["task1_anthropic_direct"] = task1_direct_adapter("claude", "claude-3-5-haiku-20241022")
            except Exception as exc:
                report["task1_anthropic_direct"] = {"error": str(exc)}
        else:
            report["task1_anthropic_direct"] = {"skipped": "ANTHROPIC_API_KEY missing"}
        if os.getenv("GOOGLE_API_KEY"):
            try:
                report["task1_gemini_direct"] = task1_direct_adapter("gemini", "gemini-2.0-flash")
            except Exception as exc:
                report["task1_gemini_direct"] = {"error": str(exc)}
        else:
            report["task1_gemini_direct"] = {"skipped": "GOOGLE_API_KEY missing"}

    if args.task in ("all", "2"):
        report["task2_session"] = task2_session(args.scratch)

    if args.task in ("all", "3"):
        report["task3_regression"] = task3_regression(args.scratch, args.repo)

    if args.task in ("all", "4"):
        report["task4_semantic"] = task4_semantic(args.scratch)
        report["task4_otel"] = task4_otel(Path(args.scratch / "otel_scratch"))

    if args.task in ("all", "5"):
        report["task5_cross_model"] = task5_cross_model(args.scratch)

    args.results.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
