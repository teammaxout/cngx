#!/usr/bin/env python3
"""Exercise action.yml logic locally (approximates GitHub Actions composite steps)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "examples" / "contracts" / "basic_reasoning.yaml"
CODING_POLICY = ROOT / "examples" / "contracts" / "coding_agent_verification.yaml"
UNVERIFIED = ROOT / "tests" / "fixtures" / "agent_outputs" / "unverified_patch.txt"
VERIFIED = ROOT / "tests" / "fixtures" / "agent_outputs" / "verified_fix.txt"
PROMPT_FILE = ROOT / "tests" / "fixtures" / "action_prompt.txt"


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


def check_offline_output_file(
    output_file: Path,
    policy: Path,
    *,
    prompt: str | None = None,
    prompt_file: Path | None = None,
    json_output: bool = False,
) -> int:
    """Mirror action.yml offline path: --output-file plus optional prompt context."""
    cmd = [
        "cngx",
        "check",
        "-c",
        str(policy),
        "--output-file",
        str(output_file),
        "--task",
        "offline_policy_check",
    ]
    if prompt_file is not None:
        cmd.extend(["--prompt-file", str(prompt_file)])
    elif prompt is not None:
        cmd.extend(["--prompt", prompt])
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

    if UNVERIFIED.is_file() and CODING_POLICY.is_file():
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(UNVERIFIED.read_text(encoding="utf-8"))
            staged = Path(f.name)
        try:
            code = check_offline_output_file(
                staged,
                CODING_POLICY,
                prompt="Fix the pagination bug and run tests before merge",
            )
            if code != 1:
                print(
                    f"FAIL: offline unverified should block (exit 1), got {code}", file=sys.stderr
                )
                return 1
        finally:
            staged.unlink(missing_ok=True)

        code = check_offline_output_file(
            VERIFIED,
            CODING_POLICY,
            prompt_file=PROMPT_FILE if PROMPT_FILE.is_file() else None,
            prompt=(
                "Fix the pagination bug and run tests before merge"
                if not PROMPT_FILE.is_file()
                else None
            ),
        )
        if code != 0:
            print(f"FAIL: offline verified should pass (exit 0), got {code}", file=sys.stderr)
            return 1

    # verify flow (primary path): a real log with failures must block,
    # a passing log must verify.
    with tempfile.TemporaryDirectory() as tmp:
        fail_log = Path(tmp) / "fail.log"
        fail_log.write_text("2 failed, 1 passed in 0.4s", encoding="utf-8")
        code = subprocess.run(
            ["cngx", "verify", "--claim", "all tests pass", "--evidence-file", str(fail_log)],
            cwd=ROOT,
            check=False,
        ).returncode
        if code != 1:
            print(f"FAIL: verify should block failing log (exit 1), got {code}", file=sys.stderr)
            return 1

        pass_log = Path(tmp) / "pass.log"
        pass_log.write_text("=== 5 passed in 0.4s ===", encoding="utf-8")
        code = subprocess.run(
            ["cngx", "verify", "--claim", "all tests pass", "--evidence-file", str(pass_log)],
            cwd=ROOT,
            check=False,
        ).returncode
        if code != 0:
            print(f"FAIL: verify should pass passing log (exit 0), got {code}", file=sys.stderr)
            return 1

    print("action.yml local smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
