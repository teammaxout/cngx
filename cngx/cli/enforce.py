"""Enforce command for cngx CLI - Runtime contract enforcement."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("run")
def enforce_run(
    prompt: str = typer.Argument(..., help="The prompt to send to the model"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Path to contract YAML/JSON file"),
    task_id: str = typer.Option("default", "--task", "-t", help="Task identifier"),
    model: str = typer.Option("gemini-flash-latest", "--model", "-m", help="Model to use"),
    adapter: str = typer.Option("gemini", "--adapter", "-a", help="Adapter (openai, gemini, mock)"),
    system: Optional[str] = typer.Option(None, "--system", "-s", help="System message"),
    strict: bool = typer.Option(True, "--strict/--lenient", help="Fail on any violation"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Execute a prompt and enforce behavior contract.

    If the model's behavior violates the contract, execution fails with a detailed report.

    Example:
        cngx enforce run "Solve 2x + 5 = 13" --contract math_contract.yaml
    """
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import BehaviorContract, ContractValidator

    # Load contract
    try:
        if contract.suffix in [".yaml", ".yml"]:
            behavior_contract = BehaviorContract.from_yaml(contract)
        else:
            behavior_contract = BehaviorContract.from_json(contract)
    except Exception as e:
        console.print(f"[red]Failed to load contract: {e}[/]")
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[dim]Contract: {behavior_contract.name} v{behavior_contract.version}[/]")
        console.print("[dim]Capturing trace...[/]")

    # Capture trace
    tracer = CngxTracer(adapter=adapter, model=model)

    try:
        trace = tracer.capture(
            prompt=prompt,
            task_id=task_id,
            system_message=system,
            save=True,
        )
    except Exception as e:
        console.print(f"[red]Capture failed: {e}[/]")
        raise typer.Exit(1)

    # Get fingerprint
    fp = tracer.get_fingerprint(trace.id)
    if not fp:
        console.print("[red]Failed to generate fingerprint[/]")
        raise typer.Exit(1)

    # Validate against contract
    validator = ContractValidator()
    result = validator.validate(fp, behavior_contract, trace)

    if json_output:
        output = {
            "contract": behavior_contract.name,
            "version": behavior_contract.version,
            "trace_id": trace.id,
            "model": model,
            "passed": result.passed,
            "violations": [v.model_dump() for v in result.violations],
            "output": trace.output,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        # Show result
        if result.passed:
            console.print(
                Panel(
                    f"[green bold]CONTRACT PASSED[/]\n\n"
                    f"Contract: {behavior_contract.name} v{behavior_contract.version}\n"
                    f"Model: {model}\n"
                    f"Trace: {trace.id}\n\n"
                    f"[dim]Output:[/]\n{trace.output[:500]}{'...' if len(trace.output) > 500 else ''}",
                    title="[green]Enforcement Result[/]",
                )
            )
        else:
            # Build violation table
            table = Table(title="Violations")
            table.add_column("Severity", style="bold")
            table.add_column("Constraint")
            table.add_column("Message")
            table.add_column("Expected")
            table.add_column("Actual")

            for v in result.violations:
                severity_color = {
                    "warn": "yellow",
                    "fail": "red",
                    "critical": "red bold",
                }.get(v.severity.value, "white")

                table.add_row(
                    f"[{severity_color}]{v.severity.value.upper()}[/]",
                    v.constraint,
                    v.message,
                    str(v.expected) if v.expected else "-",
                    str(v.actual) if v.actual else "-",
                )

            console.print(
                Panel(
                    f"[red bold]CONTRACT VIOLATED[/]\n\n"
                    f"Contract: {behavior_contract.name} v{behavior_contract.version}\n"
                    f"Model: {model}\n"
                    f"Trace: {trace.id}\n\n"
                    f"Critical: {result.critical_count} | Fail: {result.fail_count} | Warn: {result.warn_count}",
                    title="[red]Enforcement Result[/]",
                )
            )
            console.print(table)

    # Exit with appropriate code
    if not result.passed and strict:
        raise typer.Exit(1)


@app.command("check")
def enforce_check(
    trace_id: str = typer.Argument(..., help="Trace ID to validate"),
    contract: Path = typer.Option(..., "--contract", "-c", help="Path to contract file"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Validate an existing trace against a contract.

    Example:
        cngx enforce check trace_math_123 --contract math_contract.yaml
    """
    from cngx.contracts import BehaviorContract, ContractValidator
    from cngx.storage.database import get_database

    # Load contract
    try:
        if contract.suffix in [".yaml", ".yml"]:
            behavior_contract = BehaviorContract.from_yaml(contract)
        else:
            behavior_contract = BehaviorContract.from_json(contract)
    except Exception as e:
        console.print(f"[red]Failed to load contract: {e}[/]")
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
        console.print("[red]No fingerprint found for this trace[/]")
        raise typer.Exit(1)

    # Validate
    validator = ContractValidator()
    result = validator.validate(fp, behavior_contract, trace)

    if json_output:
        print(
            json.dumps(
                {
                    "passed": result.passed,
                    "violations": [v.model_dump() for v in result.violations],
                },
                indent=2,
                default=str,
            )
        )
    else:
        console.print(result.report())

    if not result.passed:
        raise typer.Exit(1)


@app.command("compare")
def enforce_compare(
    contract: Path = typer.Option(..., "--contract", "-c", help="Path to contract file"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to test"),
    models: str = typer.Option(..., "--models", help="Comma-separated list of models"),
    adapters: str = typer.Option(
        "gemini", "--adapters", help="Comma-separated adapters (matched to models)"
    ),
    task_id: str = typer.Option("compare", "--task", "-t", help="Task identifier"),
) -> None:
    """Compare policy results across multiple models.

    Example:
        cngx enforce compare --contract reasoning.yaml --prompt "Explain X" --models gpt-4o,gemini-flash-latest
    """
    import time

    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import BehaviorContract, ContractValidator

    # Load contract
    try:
        if contract.suffix in [".yaml", ".yml"]:
            behavior_contract = BehaviorContract.from_yaml(contract)
        else:
            behavior_contract = BehaviorContract.from_json(contract)
    except Exception as e:
        console.print(f"[red]Failed to load contract: {e}[/]")
        raise typer.Exit(1)

    model_list = [m.strip() for m in models.split(",")]
    adapter_list = [a.strip() for a in adapters.split(",")]

    # Expand adapters if only one provided
    if len(adapter_list) == 1:
        adapter_list = adapter_list * len(model_list)

    console.print(f"[bold]Contract:[/] {behavior_contract.name} v{behavior_contract.version}")
    console.print(f"[bold]Prompt:[/] {prompt[:50]}...")
    console.print()

    # Results table
    table = Table(title="Cross-Model Policy Check")
    table.add_column("Model", style="bold")
    table.add_column("Status")
    table.add_column("Critical")
    table.add_column("Fail")
    table.add_column("Warn")
    table.add_column("Details")

    validator = ContractValidator()
    results = []

    for model, adapter in zip(model_list, adapter_list):
        console.print(f"[dim]Testing {model}...[/]")

        try:
            tracer = CngxTracer(adapter=adapter, model=model)
            trace = tracer.capture(
                prompt=prompt,
                task_id=f"{task_id}_{model.replace('-', '_')}",
                save=True,
            )
            fp = tracer.get_fingerprint(trace.id)
            result = validator.validate(fp, behavior_contract, trace)

            status = "[green]PASS[/]" if result.passed else "[red]FAIL[/]"
            details = ", ".join([v.constraint for v in result.violations[:3]])
            if len(result.violations) > 3:
                details += f" (+{len(result.violations) - 3})"

            table.add_row(
                model,
                status,
                str(result.critical_count),
                str(result.fail_count),
                str(result.warn_count),
                details or "-",
            )
            results.append((model, result))

        except Exception as e:
            table.add_row(model, "[yellow]ERROR[/]", "-", "-", "-", str(e)[:50])

        time.sleep(2)  # Rate limiting

    console.print()
    console.print(table)

    # Summary
    passed = sum(1 for _, r in results if r.passed)
    console.print(f"\n[bold]Summary:[/] {passed}/{len(model_list)} models passed the contract")


@app.callback()
def callback() -> None:
    """Enforce behavior contracts on LLM outputs."""
    pass
