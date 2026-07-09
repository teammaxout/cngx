#!/usr/bin/env python3
"""One-shot pre-launch probe: wrap + pin + submit dry-run. Never prints API keys."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = "launch-live-baseline"
SESSION = "launch-live-session"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    scratch = Path(os.environ.get("CNGX_LAUNCH_SCRATCH", REPO / ".launch-scratch"))
    scratch.mkdir(parents=True, exist_ok=True)

    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        if not os.environ.get(name):
            print(f"MISSING {name}", file=sys.stderr)
            return 2
        print(f"OK {name} present ({len(os.environ[name])} chars)")

    init = _run([sys.executable, "-m", "cngx.cli.main", "init", "--yes"], scratch)
    if init.returncode != 0:
        print(init.stderr or init.stdout, file=sys.stderr)
        return init.returncode

    openai_probe = scratch / "openai_probe.py"
    openai_probe.write_text(
        """from openai import OpenAI
client = OpenAI()
r = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "What is 17+25? Reply with only the integer."}],
    max_tokens=16,
)
print(r.choices[0].message.content.strip())
""",
        encoding="utf-8",
    )

    anthropic_probe = scratch / "anthropic_probe.py"
    anthropic_probe.write_text(
        """import anthropic
client = anthropic.Anthropic()
r = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=16,
    messages=[{"role": "user", "content": "What is 9+8? Reply with only the integer."}],
)
print(r.content[0].text.strip())
""",
        encoding="utf-8",
    )

    w1 = _run(
        [
            sys.executable,
            "-m",
            "cngx.cli.main",
            "wrap",
            "--session-id",
            SESSION,
            "--",
            sys.executable,
            str(openai_probe),
        ],
        scratch,
    )
    print(w1.stdout)
    if w1.returncode != 0:
        print(w1.stderr, file=sys.stderr)
        return w1.returncode

    pin = _run(
        [sys.executable, "-m", "cngx.cli.main", "pin", "--label", BASELINE],
        scratch,
    )
    print(pin.stdout)
    if pin.returncode != 0:
        print(pin.stderr, file=sys.stderr)
        return pin.returncode

    w2 = _run(
        [
            sys.executable,
            "-m",
            "cngx.cli.main",
            "wrap",
            "--session-id",
            SESSION,
            "--",
            sys.executable,
            str(anthropic_probe),
        ],
        scratch,
    )
    print(w2.stdout)
    if w2.returncode != 0:
        print(w2.stderr, file=sys.stderr)
        return w2.returncode

    dry = _run(
        [
            sys.executable,
            "-m",
            "cngx.cli.main",
            "submit",
            "--baseline",
            BASELINE,
            "--dry-run",
            "--limit",
            "1",
        ],
        scratch,
    )
    print(dry.stdout)
    if dry.returncode != 0:
        print(dry.stderr, file=sys.stderr)
        return dry.returncode

    # Parse JSON from dry-run output for allowlist check
    blob = dry.stdout
    start = blob.find("{")
    end = blob.rfind("}") + 1
    if start < 0 or end <= start:
        print("Could not parse dry-run JSON", file=sys.stderr)
        return 1
    payload = json.loads(blob[start:end])
    if isinstance(payload, list):
        payload = payload[0]
    allowed = {
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
    keys = set(payload.keys())
    if keys != allowed:
        print(f"ALLOWLIST FAIL extra={keys - allowed} missing={allowed - keys}", file=sys.stderr)
        return 1
    print("ALLOWLIST OK", json.dumps(payload, indent=2))

    if os.environ.get("CNGX_LAUNCH_SUBMIT") == "1":
        sub = _run(
            [
                sys.executable,
                "-m",
                "cngx.cli.main",
                "submit",
                "--baseline",
                BASELINE,
                "--yes",
                "--limit",
                "1",
            ],
            scratch,
        )
        print(sub.stdout)
        if sub.returncode != 0:
            print(sub.stderr, file=sys.stderr)
            return sub.returncode
        print("SUBMIT OK")

    # Gemini direct adapter smoke (proxy has no Gemini route)
    from cngx.capture.tracer import CngxTracer

    tracer = CngxTracer(adapter="gemini", model="gemini-2.0-flash")
    trace = tracer.capture(
        prompt="What is 3+4? Reply with only the integer.",
        task_id="launch-gemini-smoke",
        save=False,
    )
    print(f"GEMINI OK model={trace.model} len={len(trace.output or '')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
