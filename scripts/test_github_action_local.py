#!/usr/bin/env python3
"""Exercise action.yml logic locally (approximates GitHub Actions composite steps)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "examples" / "contracts" / "basic_reasoning.yaml"


def run(cmd: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def install_editable() -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    run([sys.executable, "-m", "pip", "install", "-e", ".", "-q"])


def init_cngx() -> None:
    run(["cngx", "init", "--yes"])


def check_prompt(prompt: str, *, json_output: bool = False) -> int:
    cmd = [
        "cngx",
        "check",
        "-c",
        str(POLICY),
        "--model",
        "mock-model",
        "--adapter",
        "mock",
        "--task",
        "policy_check",
    ]
    if json_output:
        cmd.append("--json")
    cmd.append(prompt)
    print("+", " ".join(cmd[:8]), "<prompt>", flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def check_prompt_file(path: Path) -> int:
    prompt = path.read_text(encoding="utf-8")
    return check_prompt(prompt)


def check_offline(
    prompt: str,
    output_file: Path,
    policy: Path = POLICY,
    *,
    json_output: bool = False,
) -> int:
    cmd = [
        "cngx",
        "check",
        "-c",
        str(policy),
        "--prompt",
        prompt,
        "--output-file",
        str(output_file),
        "--task",
        "offline_policy_check",
    ]
    if json_output:
        cmd.append("--json")
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def main() -> int:
    if not POLICY.is_file():
        print(f"policy missing: {POLICY}", file=sys.stderr)
        return 1

    print("=== action.yml local smoke (editable install) ===")
    install_editable()
    init_cngx()

    code = check_prompt("What is 15 * 7? Show your reasoning step by step.")
    if code != 0:
        print(f"FAIL: inline prompt exit {code}", file=sys.stderr)
        return code

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("What is 2+2? Show your work step by step.")
        prompt_file = Path(f.name)

    try:
        code = check_prompt_file(prompt_file)
        if code != 0:
            print(f"FAIL: prompt-file exit {code}", file=sys.stderr)
            return code
    finally:
        prompt_file.unlink(missing_ok=True)

    code = check_prompt("What is 2+2?", json_output=True)
    if code != 0:
        print(f"FAIL: json output exit {code}", file=sys.stderr)
        return code

    shallow_output = ROOT / "tests" / "fixtures" / "shallow_agent_output.txt"
    policy_path = ROOT / "examples" / "contracts" / "coding_agent_fix.yaml"
    if shallow_output.is_file() and policy_path.is_file():
        code = check_offline(
            "Fix the pagination bug and run tests before merge",
            shallow_output,
            policy=policy_path,
        )
        if code != 1:
            print(
                f"FAIL: offline shallow agent should block (exit 1), got {code}",
                file=sys.stderr,
            )
            return 1

    print("action.yml local smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
