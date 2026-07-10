"""cngx check, policy validation for CI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console(stderr=True)
app = typer.Typer(
    help="Check one prompt/response against a behavior policy (message one, no baseline)"
)


def _load_policy(path: Path):
    from cngx.contracts import BehaviorContract

    if path.suffix in (".yaml", ".yml"):
        return BehaviorContract.from_yaml(path)
    return BehaviorContract.from_json(path)


def _load_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _resolve_prompt(
    prompt_arg: Optional[str],
    prompt_opt: Optional[str],
    prompt_file: Optional[Path],
    *,
    required: bool,
) -> tuple[str, Optional[int]]:
    if prompt_file is not None:
        if not prompt_file.is_file():
            console.print(f"[red]prompt-file not found: {prompt_file}[/]")
            return "", 2
        text = _load_text_file(prompt_file)
    else:
        text = prompt_arg or prompt_opt or ""

    if required and (not text or not text.strip()):
        console.print(
            "[red]Prompt is required (positional argument, --prompt, or --prompt-file)[/]"
        )
        return "", 2
    return text, None


def _resolve_output_text(
    output_file: Optional[Path],
    stdin: bool,
) -> tuple[str, Optional[int]]:
    if output_file is not None and stdin:
        console.print("[red]Use only one of --output-file or --stdin[/]")
        return "", 2
    if stdin:
        return sys.stdin.read(), None
    if output_file is not None:
        if not output_file.is_file():
            console.print(f"[red]output-file not found: {output_file}[/]")
            return "", 2
        return _load_text_file(output_file), None
    console.print("[red]Agent output required: use --output-file or --stdin[/]")
    return "", 2


def run_policy_check(
    policy: Path,
    prompt: Optional[str] = None,
    prompt_opt: Optional[str] = None,
    prompt_file: Optional[Path] = None,
    output_file: Optional[Path] = None,
    stdin: bool = False,
    evidence_file: Optional[Path] = None,
    model: str = "mock-model",
    adapter: str = "mock",
    task_id: str = "policy_check",
    json_output: bool = False,
) -> int:
    """Route to offline ingest or online capture based on output inputs."""
    offline = output_file is not None or stdin
    prompt_text, prompt_err = _resolve_prompt(prompt, prompt_opt, prompt_file, required=not offline)
    if prompt_err is not None:
        return prompt_err

    if offline:
        output_text, output_err = _resolve_output_text(output_file, stdin)
        if output_err is not None:
            return output_err
        offline_model = model if model != "mock-model" else "agent-output"
        return run_offline_check(
            prompt=prompt_text,
            output=output_text,
            policy=policy,
            model=offline_model,
            task_id=task_id,
            json_output=json_output,
            evidence_file=evidence_file,
        )

    if evidence_file is not None:
        console.print("[red]--evidence-file is only valid with --output-file or --stdin[/]")
        return 2

    return run_check(
        prompt_text,
        policy,
        model,
        adapter,
        task_id,
        json_output,
    )


def run_offline_check(
    prompt: str,
    output: str,
    policy: Path,
    model: str = "agent-output",
    task_id: str = "policy_check",
    json_output: bool = False,
    evidence_file: Optional[Path] = None,
) -> int:
    """Fingerprint and gate existing agent output. No LLM calls."""
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate
    from cngx.enforcement.evidence import check_evidence_text, first_result_snippet

    try:
        behavior_policy = _load_policy(policy)
    except Exception as e:
        console.print(f"[red]Could not load policy: {e}[/]")
        return 2

    evidence_payload = None
    gated_output = output
    if evidence_file is not None:
        if not evidence_file.is_file():
            console.print(f"[red]evidence-file not found: {evidence_file}[/]")
            return 2
        evidence_text = _load_text_file(evidence_file)
        evidence_check = check_evidence_text(evidence_text)
        evidence_payload = {
            "path": str(evidence_file),
            "ok": evidence_check.ok,
            "reasons": list(evidence_check.reasons),
        }
        if not evidence_check.ok:
            if json_output:
                print(
                    json.dumps(
                        {
                            "status": "blocked",
                            "exit_code": 1,
                            "evidence": evidence_payload,
                            "policy": behavior_policy.name,
                        },
                        indent=2,
                    )
                )
            else:
                console.print("[red]STATUS: BLOCKED[/] (evidence check failed)")
                for reason in evidence_check.reasons:
                    console.print(f"  - {reason}")
            return 1
        # Inject a concrete result line from the CI log into the text under
        # policy review so agents that reasoned well but omitted pasting
        # pytest output can still satisfy required_patterns.
        snippet = first_result_snippet(evidence_text)
        if snippet:
            evidence_payload["snippet"] = snippet
            gated_output = f"{output.rstrip()}\n\n[cngx evidence]\n{snippet}\n"

    trace, fp = CngxTracer.ingest_output(
        gated_output,
        prompt=prompt,
        task_id=task_id,
        model=model,
    )

    gate = DeploymentGate()
    result = gate.check(fp, behavior_policy, trace)

    if json_output:
        out = result.to_ci_output()
        out["policy"] = out.pop("contract", behavior_policy.name)
        if evidence_payload is not None:
            out["evidence"] = evidence_payload
        print(json.dumps(out, indent=2, default=str))
    else:
        console.print(_format_policy_report(result))
        if evidence_payload is not None and evidence_payload["ok"]:
            console.print("[green]Evidence check: OK[/] " f"({evidence_payload['path']})")
        elif evidence_file is None:
            console.print(
                "[dim]note: this scores the text of the output heuristically and can be "
                "gamed by fabricated claims. To bind a claim to a real run, use "
                "[cyan]cngx verify -- <command>[/].[/]"
            )

    return result.exit_code


def run_check(
    prompt: str,
    policy: Path,
    model: str = "mock-model",
    adapter: str = "mock",
    task_id: str = "policy_check",
    json_output: bool = False,
) -> int:
    """Check prompt against policy via live capture. Returns exit code."""
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    try:
        behavior_policy = _load_policy(policy)
    except Exception as e:
        console.print(f"[red]Could not load policy: {e}[/]")
        return 2

    tracer = CngxTracer(adapter=adapter, model=model)
    try:
        trace = tracer.capture(prompt=prompt, task_id=task_id, save=True)
        fp = tracer.get_fingerprint(trace.id)
    except Exception as e:
        console.print(f"[red]Capture failed: {e}[/]")
        return 2

    if not fp:
        console.print("[red]Fingerprint generation failed[/]")
        return 2

    gate = DeploymentGate()
    result = gate.check(fp, behavior_policy, trace)

    if json_output:
        out = result.to_ci_output()
        out["policy"] = out.pop("contract", behavior_policy.name)
        print(json.dumps(out, indent=2, default=str))
    else:
        console.print(_format_policy_report(result))

    return result.exit_code


def _format_policy_report(result) -> str:
    """User-facing report, always says policy, never gate/contract/compliance."""
    lines = [
        "=" * 60,
        "cngx policy check",
        "=" * 60,
        "",
        f"Policy: {result.contract_name} v{result.contract_version}",
        f"Hash: {result.contract_hash}",
        f"Model: {result.model}",
        f"Trace: {result.trace_id}",
        "",
    ]
    if result.blocked:
        lines.extend(
            [
                "STATUS: BLOCKED",
                "",
                f"Blocking issues: {result.block_count}",
                f"Other failures: {result.fail_count}",
                f"Warnings: {result.warn_count}",
                "",
            ]
        )
        for v in result.violations:
            if v.severity.value == "block":
                lines.append(f"  [BLOCK] {v.message}")
    elif not result.passed:
        lines.extend(
            [
                "STATUS: FAILED",
                "",
                f"Failures: {result.fail_count}",
                f"Warnings: {result.warn_count}",
                "",
            ]
        )
    else:
        lines.extend(["STATUS: PASSED", "", f"Warnings: {result.warn_count}", ""])

    if result.violations and (result.blocked or not result.passed):
        lines.append("Details:")
        for v in result.violations:
            lines.append(f"  [{v.severity.value}] {v.message}")

    lines.extend(["=" * 60, f"EXIT CODE: {result.exit_code}", "=" * 60])
    return "\n".join(lines)


@app.command()
def check(
    prompt: Optional[str] = typer.Argument(
        None,
        help="Prompt or task description",
    ),
    policy: Path = typer.Option(..., "--policy", "-c", help="Policy YAML file"),
    prompt_opt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Task prompt when not passed as a positional argument",
    ),
    prompt_file: Optional[Path] = typer.Option(
        None,
        "--prompt-file",
        help="File with task prompt context (stored on trace, not sent to any API)",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        help="File with agent output to gate offline (no LLM call)",
    ),
    stdin: bool = typer.Option(
        False,
        "--stdin",
        help="Read agent output from stdin for offline gating",
    ),
    evidence_file: Optional[Path] = typer.Option(
        None,
        "--evidence-file",
        help=(
            "CI/test log to cross-check (must contain e.g. 'N passed'); "
            "offline only. Valid logs inject a result snippet into the gated text"
        ),
    ),
    model: str = typer.Option("mock-model", "--model", "-m"),
    adapter: str = typer.Option("mock", "--adapter", "-a", help="mock, openai, gemini, claude"),
    task_id: str = typer.Option("policy_check", "--task", "-t"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Check agent output against a behavior policy.

    Online (default): capture a new model response, then gate it.
    Offline: pass --output-file or --stdin to gate existing output with zero provider calls.

    Exit codes: 0 pass, 1 blocked, 2 failed (soft violations or input errors).
    """
    raise typer.Exit(
        run_policy_check(
            policy=policy,
            prompt=prompt,
            prompt_opt=prompt_opt,
            prompt_file=prompt_file,
            output_file=output_file,
            stdin=stdin,
            evidence_file=evidence_file,
            model=model,
            adapter=adapter,
            task_id=task_id,
            json_output=json_output,
        )
    )


if __name__ == "__main__":
    app()
