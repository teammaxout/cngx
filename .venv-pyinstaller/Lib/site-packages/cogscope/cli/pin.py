"""Pin command for Cogscope CLI."""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("create")
def create_pin(
    trace_id: str = typer.Argument(..., help="Trace ID to pin as baseline"),
    name: str = typer.Option(..., "--name", "-n", help="Name for the baseline"),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Description"),
) -> None:
    """Pin a trace as a baseline behavior.

    Example:
        cogscope pin create trace_abc123 --name "math_baseline_v1"
    """
    from cogscope.versioning.pinning import PinningManager

    manager = PinningManager()

    try:
        baseline = manager.pin(
            trace_id=trace_id,
            name=name,
            description=description,
        )
        console.print(f"[green]✓[/] Created baseline '{name}' from trace {trace_id}")
        console.print(f"  ID: {baseline.id}")
        console.print(f"  Task: {baseline.task_id}")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("list")
def list_pins(
    task_id: Optional[str] = typer.Option(None, "--task", "-t", help="Filter by task"),
) -> None:
    """List all pinned baselines."""
    from cogscope.versioning.pinning import PinningManager

    manager = PinningManager()
    pins = manager.list_pins(task_id)

    if not pins:
        console.print("[yellow]No baselines found.[/]")
        return

    table = Table(title="Pinned Baselines")
    table.add_column("Name", style="cyan")
    table.add_column("Task")
    table.add_column("Trace ID")
    table.add_column("Created")
    table.add_column("Description")

    for pin in pins:
        table.add_row(
            pin.name,
            pin.task_id,
            pin.trace_id[:20] + "...",
            pin.created_at.strftime("%Y-%m-%d %H:%M"),
            (pin.description or "")[:30],
        )

    console.print(table)


@app.command("show")
def show_pin(
    name: str = typer.Argument(..., help="Baseline name"),
) -> None:
    """Show details of a pinned baseline."""
    from rich.panel import Panel

    from cogscope.versioning.baseline import BaselineManager
    from cogscope.versioning.pinning import PinningManager

    manager = PinningManager()
    baseline_manager = BaselineManager()

    try:
        pin = manager.get_pin(name)
        fp = baseline_manager.get_fingerprint(name)

        console.print(
            Panel(
                f"[bold]Name:[/] {pin.name}\n"
                f"[bold]ID:[/] {pin.id}\n"
                f"[bold]Task:[/] {pin.task_id}\n"
                f"[bold]Trace:[/] {pin.trace_id}\n"
                f"[bold]Created:[/] {pin.created_at}\n"
                f"[bold]Description:[/] {pin.description or 'None'}\n\n"
                f"[bold]Fingerprint:[/]\n"
                f"  Depth: {fp.depth}\n"
                f"  Steps: {fp.total_steps}\n"
                f"  Tools: {fp.tool_call_count}\n"
                f"  Corrections: {fp.correction_count}\n"
                f"  Verification: {fp.verification_steps}\n"
                f"  Hedging ratio: {fp.hedging_ratio:.2f}\n"
                f"  Signature: {fp.signature_hash}",
                title=f"[green]Baseline: {name}[/]",
            )
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("check")
def check_pin(
    name: str = typer.Argument(..., help="Baseline name"),
    trace_id: str = typer.Argument(..., help="Trace ID to check"),
) -> None:
    """Check if a trace matches a pinned baseline."""
    from cogscope.versioning.pinning import PinningManager

    manager = PinningManager()

    try:
        result = manager.check_against_pin(name, trace_id)

        status_color = "green" if result["passed"] else "red"
        status_text = result["status"]

        console.print(f"[{status_color}]{status_text}[/]")
        console.print(f"  Drift score: {result['drift_score']:.1%}")
        console.print(f"  Changes: {result['changes_count']}")
        console.print(f"  Breaking: {result['breaking_changes']}")
        console.print(f"  Summary: {result['summary']}")

        if not result["passed"]:
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("remove")
def remove_pin(
    name: str = typer.Argument(..., help="Baseline name to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove (deactivate) a pinned baseline."""
    from cogscope.versioning.pinning import PinningManager

    if not force:
        confirm = typer.confirm(f"Remove baseline '{name}'?")
        if not confirm:
            raise typer.Abort()

    manager = PinningManager()

    try:
        manager.unpin(name)
        console.print(f"[green]✓[/] Removed baseline '{name}'")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.callback()
def callback() -> None:
    """Pin baseline behaviors for comparison."""
    pass
