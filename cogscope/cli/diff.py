"""Diff command for Cogscope CLI."""

import json as json_lib
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("traces")
def diff_traces(
    baseline_id: str = typer.Argument(..., help="Baseline trace ID"),
    current_id: str = typer.Argument(..., help="Current trace ID"),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Compare two traces by ID.

    Example:
        cogscope diff traces trace_abc123 trace_def456
    """
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter
    from cogscope.fingerprint.extractor import FingerprintExtractor
    from cogscope.storage.database import get_database

    db = get_database()
    extractor = FingerprintExtractor()
    engine = DiffEngine()
    formatter = DiffFormatter()

    try:
        # Get or extract fingerprints
        baseline_fp = db.get_fingerprint_by_trace(baseline_id)
        if not baseline_fp:
            baseline_trace = db.get_trace(baseline_id)
            baseline_fp = extractor.extract(baseline_trace)

        current_fp = db.get_fingerprint_by_trace(current_id)
        if not current_fp:
            current_trace = db.get_trace(current_id)
            current_fp = extractor.extract(current_trace)

        # Compute diff
        diff = engine.diff(baseline_fp, current_fp)

        if json:
            print(json_lib.dumps(formatter.format_dict(diff), indent=2))
        else:
            formatter.format_rich(diff)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("baseline")
def diff_baseline(
    baseline_name: str = typer.Argument(..., help="Baseline name"),
    trace_id: str = typer.Argument(..., help="Trace ID to compare"),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Compare a trace against a named baseline.

    Example:
        cogscope diff baseline math_v1 trace_abc123
    """
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter
    from cogscope.fingerprint.extractor import FingerprintExtractor
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

    db = get_database()
    baseline_manager = BaselineManager()
    extractor = FingerprintExtractor()
    engine = DiffEngine()
    formatter = DiffFormatter()

    try:
        # Get baseline fingerprint
        baseline_fp = baseline_manager.get_fingerprint(baseline_name)

        # Get current fingerprint
        current_fp = db.get_fingerprint_by_trace(trace_id)
        if not current_fp:
            current_trace = db.get_trace(trace_id)
            current_fp = extractor.extract(current_trace)

        # Compute diff
        diff = engine.diff(baseline_fp, current_fp)

        if json:
            print(json_lib.dumps(formatter.format_dict(diff), indent=2))
        else:
            console.print(f"\n[bold]Comparing against baseline: {baseline_name}[/]\n")
            formatter.format_rich(diff)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("latest")
def diff_latest(
    task_id: str = typer.Argument(..., help="Task ID"),
    baseline_name: Optional[str] = typer.Option(
        None, "--baseline", "-b", help="Baseline to compare against"
    ),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Compare the latest trace for a task against baseline or previous.

    Example:
        cogscope diff latest math --baseline math_v1
    """
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

    db = get_database()
    engine = DiffEngine()
    formatter = DiffFormatter()

    try:
        # Get latest traces
        traces = db.get_traces_by_task(task_id, limit=2)
        if len(traces) < 1:
            console.print(f"[yellow]No traces found for task '{task_id}'[/]")
            raise typer.Exit(1)

        current_fp = db.get_fingerprint_by_trace(traces[0].id)

        if baseline_name:
            baseline_manager = BaselineManager()
            baseline_fp = baseline_manager.get_fingerprint(baseline_name)
            console.print(f"\n[bold]Latest vs baseline: {baseline_name}[/]\n")
        elif len(traces) >= 2:
            baseline_fp = db.get_fingerprint_by_trace(traces[1].id)
            console.print("\n[bold]Latest vs previous trace[/]\n")
        else:
            console.print("[yellow]Need at least 2 traces or a baseline to compare[/]")
            raise typer.Exit(1)

        if not current_fp or not baseline_fp:
            console.print("[red]Fingerprints not found[/]")
            raise typer.Exit(1)

        diff = engine.diff(baseline_fp, current_fp)

        if json:
            print(json_lib.dumps(formatter.format_dict(diff), indent=2))
        else:
            formatter.format_rich(diff)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.callback()
def callback() -> None:
    """Compare behavioral fingerprints."""
    pass
