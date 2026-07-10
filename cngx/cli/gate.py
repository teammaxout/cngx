"""cngx Gate, behavioral contract enforcement CLI.

Primary commands for deployment blocking and CI/CD integration.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="gate",
    help="behavioral contract enforcement - Block deployment on contract violations",
)
console = Console(stderr=True)


def _load_contract(path: Path):
    """Load a contract from file."""
    from cngx.contracts import BehaviorContract

    if path.suffix in [".yaml", ".yml"]:
        return BehaviorContract.from_yaml(path)
    else:
        return BehaviorContract.from_json(path)


def _output_result(result, json_output: bool, quiet: bool):
    """Output gate result appropriately."""
    if json_output:
        print(json.dumps(result.to_ci_output(), indent=2, default=str))
    elif quiet:
        if result.blocked:
            console.print(f"[red bold]BLOCKED[/]: {result.contract_name}")
        elif not result.passed:
            console.print(f"[yellow]FAILED[/]: {result.contract_name}")
        else:
            console.print(f"[green]PASSED[/]: {result.contract_name}")
    else:
        console.print(result.report())


@app.command("check")
def gate_check(
    prompt: str = typer.Argument(..., help="Prompt to test"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Contract file"),
    model: str = typer.Option("gemini-flash-latest", "--model", "-m"),
    adapter: str = typer.Option(
        "gemini", "--adapter", "-a", help="Adapter (openai, gemini, claude, mock)"
    ),
    task_id: str = typer.Option("gate_check", "--task", "-t"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output for CI"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
) -> None:
    """Check if a prompt passes a behavior contract.

    Exit codes:
      0 = PASSED (deployment allowed)
      1 = BLOCKED (deployment must be prevented)
      2 = FAILED (violations but not blocking)

    Example:
        cngx gate check "Solve x^2 = 16" -c math.yaml
    """
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    # Load contract
    try:
        behavior_contract = _load_contract(contract)
    except Exception as e:
        console.print(f"[red]Contract load failed: {e}[/]")
        raise typer.Exit(1)

    if not quiet and not json_output:
        console.print(f"[dim]Contract: {behavior_contract.name} v{behavior_contract.version}[/]")
        console.print(f"[dim]Model: {model}[/]")
        console.print("[dim]Capturing...[/]")

    # Capture trace
    tracer = CngxTracer(adapter=adapter, model=model)

    try:
        trace = tracer.capture(prompt=prompt, task_id=task_id, save=True)
        fp = tracer.get_fingerprint(trace.id)
    except Exception as e:
        console.print(f"[red]Capture failed: {e}[/]")
        raise typer.Exit(1)

    if not fp:
        console.print("[red]Fingerprint generation failed[/]")
        raise typer.Exit(1)

    # Run gate
    gate = DeploymentGate()
    result = gate.check(fp, behavior_contract, trace)

    _output_result(result, json_output, quiet)
    raise typer.Exit(result.exit_code)


@app.command("ci")
def gate_ci(
    prompt: str = typer.Argument(..., help="Prompt to test"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Contract file"),
    model: str = typer.Option("gemini-flash-latest", "--model", "-m"),
    adapter: str = typer.Option(
        "gemini", "--adapter", "-a", help="Adapter (openai, gemini, claude, mock)"
    ),
    task_id: str = typer.Option("ci_check", "--task", "-t"),
) -> None:
    """CI/CD mode - JSON output, non-interactive, exit codes.

    Designed for GitHub Actions, GitLab CI, etc.

    Exit codes:
      0 = PASSED
      1 = BLOCKED (hard failure)
      2 = FAILED (soft failure)

    Example (GitHub Actions):
        - run: cngx gate ci "$PROMPT" -c contracts/math.yaml
    """
    # Suppress warnings in CI
    import warnings

    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    warnings.filterwarnings("ignore")

    # Load contract
    try:
        behavior_contract = _load_contract(contract)
    except Exception as e:
        print(json.dumps({"error": str(e), "exit_code": 1}))
        raise typer.Exit(1)

    # Capture trace
    tracer = CngxTracer(adapter=adapter, model=model)

    try:
        trace = tracer.capture(prompt=prompt, task_id=task_id, save=True)
        fp = tracer.get_fingerprint(trace.id)
    except Exception as e:
        print(json.dumps({"error": str(e), "exit_code": 1}))
        raise typer.Exit(1)

    if not fp:
        print(json.dumps({"error": "Fingerprint generation failed", "exit_code": 1}))
        raise typer.Exit(1)

    # Run gate
    gate = DeploymentGate()
    result = gate.check(fp, behavior_contract, trace)

    # CI output
    print(json.dumps(result.to_ci_output(), indent=2, default=str))
    raise typer.Exit(result.exit_code)


@app.command("validate")
def gate_validate(
    trace_id: str = typer.Argument(..., help="Existing trace ID"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Contract file"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Validate an existing trace against a contract.

    Use when you already have a captured trace.
    """
    from cngx.contracts import DeploymentGate
    from cngx.storage.database import get_database

    # Load contract
    try:
        behavior_contract = _load_contract(contract)
    except Exception as e:
        console.print(f"[red]Contract load failed: {e}[/]")
        raise typer.Exit(1)

    # Get trace and fingerprint
    db = get_database()
    try:
        trace = db.get_trace(trace_id)
        fp = db.get_fingerprint_by_trace(trace_id)
    except Exception as e:
        console.print(f"[red]Trace not found: {e}[/]")
        raise typer.Exit(1)

    if not fp:
        console.print("[red]No fingerprint for this trace[/]")
        raise typer.Exit(1)

    # Run gate
    gate = DeploymentGate()
    result = gate.check(fp, behavior_contract, trace)

    _output_result(result, json_output, False)
    raise typer.Exit(result.exit_code)


@app.command("compare")
def gate_compare(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to test"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Contract file"),
    models: str = typer.Option(..., "--models", help="Comma-separated models"),
    adapters: str = typer.Option("gemini", "--adapters", help="Comma-separated adapters"),
) -> None:
    """Compare policy results across models.

    Shows which models pass/fail the same contract.
    Critical for detecting model upgrade regressions.
    """
    import time

    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    # Load contract
    try:
        behavior_contract = _load_contract(contract)
    except Exception as e:
        console.print(f"[red]Contract load failed: {e}[/]")
        raise typer.Exit(1)

    model_list = [m.strip() for m in models.split(",")]
    adapter_list = [a.strip() for a in adapters.split(",")]

    if len(adapter_list) == 1:
        adapter_list = adapter_list * len(model_list)

    console.print(
        Panel(
            f"[bold]Contract:[/] {behavior_contract.name} v{behavior_contract.version}\n"
            f"[bold]Prompt:[/] {prompt[:60]}...\n"
            f"[bold]Models:[/] {', '.join(model_list)}",
            title="[bold]Cross-Model Gate Comparison[/]",
        )
    )

    # Results
    table = Table(title="Gate Results")
    table.add_column("Model", style="bold")
    table.add_column("Status")
    table.add_column("BLOCK")
    table.add_column("FAIL")
    table.add_column("WARN")
    table.add_column("Exit Code")

    gate = DeploymentGate()
    any_blocked = False

    for model, adapter in zip(model_list, adapter_list):
        console.print(f"[dim]Testing {model}...[/]")

        try:
            tracer = CngxTracer(adapter=adapter, model=model)
            trace = tracer.capture(
                prompt=prompt,
                task_id=f"compare_{model.replace('-', '_')}",
                save=True,
            )
            fp = tracer.get_fingerprint(trace.id)
            result = gate.check(fp, behavior_contract, trace)

            if result.blocked:
                status = "[red bold]BLOCKED[/]"
                any_blocked = True
            elif not result.passed:
                status = "[yellow]FAILED[/]"
            else:
                status = "[green]PASSED[/]"

            table.add_row(
                model,
                status,
                str(result.block_count),
                str(result.fail_count),
                str(result.warn_count),
                str(result.exit_code),
            )
        except Exception:
            table.add_row(model, "[red]ERROR[/]", "-", "-", "-", "1")

        time.sleep(2)

    console.print()
    console.print(table)

    if any_blocked:
        console.print("\n[red bold]WARNING: Some models would be BLOCKED from deployment[/]")
        raise typer.Exit(1)


@app.callback()
def callback() -> None:
    """behavioral contract enforcement - Block deployment on contract violations."""
    pass
