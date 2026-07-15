"""cngx verify: run what the agent claimed, compare to reality, gate the merge."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)


# Minimal auto-detect: only pytest, and only when it is actually importable in
# the current environment. Everything else should be passed explicitly with --.
def _autodetect_command(cwd: Path) -> Optional[list[str]]:
    import importlib.util

    if importlib.util.find_spec("pytest") is None:
        return None
    has_tests = (cwd / "tests").is_dir() or any(cwd.glob("test_*.py")) or any(cwd.glob("*_test.py"))
    if has_tests:
        return [sys.executable, "-m", "pytest", "-q"]
    return None


def _claim_from_commit(ref: str) -> tuple[str, Optional[int]]:
    """Read a claim from a git commit message via `git log -1 --pretty=%B REF`.

    An empty ref is treated as HEAD, matching the documented default.
    """
    import subprocess

    ref = ref or "HEAD"

    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%B", ref],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        console.print("[red]git not found on PATH; cannot read --from-commit.[/]")
        return "", 2
    if result.returncode != 0:
        detail = result.stderr.strip() or f"no such commit: {ref}"
        console.print(f"[red]could not read commit {ref}: {detail}[/]")
        return "", 2
    return result.stdout, None


def _claim_from_pr() -> tuple[str, Optional[int]]:
    """Read a claim from the GitHub Actions event payload (.pull_request.body)."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        console.print(
            "[red]--from-pr only works inside GitHub Actions[/] (GITHUB_EVENT_PATH is not set)."
        )
        return "", 2
    path = Path(event_path)
    if not path.is_file():
        console.print(f"[red]event payload not found: {event_path}[/]")
        return "", 2
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[red]could not read event payload: {exc}[/]")
        return "", 2
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        console.print(
            "[red]no pull_request in the event payload[/] (is this a pull_request event?)."
        )
        return "", 2
    # A PR with an empty description is valid; the claim is just empty.
    return pull_request.get("body") or "", None


def _read_claim(
    claim: Optional[str],
    output_file: Optional[Path],
    stdin: bool,
    from_commit: Optional[str],
    from_pr: bool,
) -> tuple[str, Optional[int]]:
    # Claim sources are mutually exclusive: silent precedence hides operator
    # mistakes in CI, so more than one selected source is a usage error (exit 2).
    active = []
    if claim is not None:
        active.append("--claim")
    if output_file is not None:
        active.append("--output-file")
    if stdin:
        active.append("--stdin")
    if from_commit is not None:
        active.append("--from-commit")
    if from_pr:
        active.append("--from-pr")

    if len(active) > 1:
        console.print(
            f"[red]Conflicting claim sources: {', '.join(active)}.[/] "
            "Pass exactly one of --claim, --output-file, --stdin, --from-commit, --from-pr."
        )
        return "", 2

    if stdin:
        return sys.stdin.read(), None
    if output_file is not None:
        if not output_file.is_file():
            console.print(f"[red]output-file not found: {output_file}[/]")
            return "", 2
        return output_file.read_text(encoding="utf-8"), None
    if from_commit is not None:
        return _claim_from_commit(from_commit)
    if from_pr:
        return _claim_from_pr()
    return claim or "", None


def _tail(text: str, lines: int = 25) -> str:
    kept = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(kept[-lines:])


def run_verify(
    command: list[str],
    claim: Optional[str] = None,
    output_file: Optional[Path] = None,
    stdin: bool = False,
    from_commit: Optional[str] = None,
    from_pr: bool = False,
    evidence_file: Optional[Path] = None,
    require_claim: bool = False,
    timeout: float = 600.0,
    json_output: bool = False,
) -> int:
    from cngx.verify.claims import extract_claim
    from cngx.verify.parsers import parse_output
    from cngx.verify.runner import run_command
    from cngx.verify.verdict import decide

    claim_text, err = _read_claim(claim, output_file, stdin, from_commit, from_pr)
    if err is not None:
        return err
    parsed_claim = extract_claim(claim_text)

    cwd = Path.cwd()
    real_output = ""
    timed_out = False
    command_label: Optional[str] = None

    if evidence_file is not None:
        if command:
            console.print("[red]Use either a command (after --) or --evidence-file, not both[/]")
            return 2
        if not evidence_file.is_file():
            console.print(f"[red]evidence-file not found: {evidence_file}[/]")
            return 2
        real_output = evidence_file.read_text(encoding="utf-8")
        result = parse_output(real_output, exit_code=None)
        command_label = f"log {evidence_file.name}"
    else:
        if not command:
            command = _autodetect_command(cwd) or []
            if not command:
                console.print(
                    "[red]Nothing to run.[/] Pass the verification command after [cyan]--[/], "
                    "e.g. [cyan]cngx verify -- pytest[/], or a real log with "
                    "[cyan]--evidence-file[/]."
                )
                return 2
            console.print(f"[dim]auto-detected: {' '.join(command)}[/]")
        run_result = run_command(command, timeout=timeout, cwd=str(cwd))
        real_output = run_result.combined
        timed_out = run_result.timed_out
        result = parse_output(real_output, exit_code=run_result.exit_code)
        command_label = " ".join(command)

    verdict = decide(
        result,
        parsed_claim,
        timed_out=timed_out,
        timeout=timeout,
        require_claim=require_claim,
        command_label=command_label,
    )

    if json_output:
        payload = verdict.to_dict()
        payload["command"] = command_label
        payload["framework"] = result.framework
        payload["claim"] = {
            "claims_success": parsed_claim.claims_success,
            "claimed_passed": parsed_claim.claimed_passed,
            "markers": list(parsed_claim.markers),
        }
        print(json.dumps(payload, indent=2))
        return verdict.exit_code

    _render(verdict, real_output)
    return verdict.exit_code


def _render(verdict, real_output: str) -> None:
    from cngx.verify.verdict import BLOCKED, VERIFIED

    if verdict.status == VERIFIED:
        border, tag = "green", "[bold green]VERIFIED[/]"
    elif verdict.status == BLOCKED:
        border, tag = "red", "[bold red]BLOCKED[/]"
    else:
        border, tag = "yellow", "[bold yellow]ERROR[/]"

    body = [f"{tag}  {verdict.headline}"]
    if verdict.reasons:
        body.append("")
        for reason in verdict.reasons:
            body.append(f"  {reason}")
    console.print(Panel("\n".join(body), border_style=border, padding=(1, 2)))

    if verdict.blocked and real_output.strip():
        console.print("[dim]--- real output (tail) ---[/]")
        console.print(_tail(real_output))
    console.print(f"[dim]exit code: {verdict.exit_code}[/]")


app = typer.Typer()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def verify(
    ctx: typer.Context,
    claim: Optional[str] = typer.Option(
        None,
        "--claim",
        "-C",
        help="Agent claim text (what it said it did). Claim sources are mutually exclusive.",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        "-o",
        help="File with the agent's message to read the claim from. "
        "Claim sources are mutually exclusive.",
    ),
    stdin: bool = typer.Option(False, "--stdin", help="Read the agent claim from stdin"),
    from_commit: Optional[str] = typer.Option(
        None,
        "--from-commit",
        metavar="REF",
        help="Read the claim from a git commit message, e.g. --from-commit HEAD. "
        "Claim sources are mutually exclusive.",
    ),
    from_pr: bool = typer.Option(
        False,
        "--from-pr",
        help="Read the claim from the GitHub Actions PR event payload. "
        "Claim sources are mutually exclusive.",
    ),
    evidence_file: Optional[Path] = typer.Option(
        None, "--evidence-file", "-e", help="Use an existing test log instead of running a command"
    ),
    require_claim: bool = typer.Option(
        False, "--require-claim", help="Also block if checks pass but the agent made no claim"
    ),
    timeout: float = typer.Option(600.0, "--timeout", help="Seconds before the command is killed"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Machine-readable output"),
) -> None:
    """Run the checks the agent claimed it ran, then compare claim to reality.

    Put the real verification command after a double dash:

      cngx verify --output-file agent.md -- pytest

    cngx runs pytest, reads what the agent said, and BLOCKS (exit 1) when the
    agent claimed success but the tests actually fail, or when its reported
    counts do not match the real run. The verdict is bound to real command
    output, so it cannot be satisfied by prose alone.

    Exit codes: 0 verified, 1 blocked, 2 usage error.
    """
    raise typer.Exit(
        run_verify(
            command=list(ctx.args),
            claim=claim,
            output_file=output_file,
            stdin=stdin,
            from_commit=from_commit,
            from_pr=from_pr,
            evidence_file=evidence_file,
            require_claim=require_claim,
            timeout=timeout,
            json_output=json_output,
        )
    )
