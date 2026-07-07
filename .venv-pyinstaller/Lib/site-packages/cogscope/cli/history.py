"""History command for Cogscope CLI."""

import json as json_lib
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("list")
def list_history(
    task_id: Optional[str] = typer.Option(None, "--task", "-t", help="Filter by task"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of traces to show"),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """List trace history.

    Example:
        cogscope history list --task math --limit 10
    """
    from cogscope.storage.database import get_database

    db = get_database()

    try:
        if task_id:
            traces = db.get_traces_by_task(task_id, limit=limit)
        else:
            traces = db.get_recent_traces(limit=limit)

        if json:
            data = []
            for trace in traces:
                fp = db.get_fingerprint_by_trace(trace.id)
                data.append(
                    {
                        "id": trace.id,
                        "task_id": trace.task_id,
                        "model": trace.model,
                        "timestamp": trace.timestamp.isoformat(),
                        "fingerprint": fp.signature_hash if fp else None,
                        "depth": fp.depth if fp else None,
                    }
                )
            print(json_lib.dumps(data, indent=2))
        else:
            if not traces:
                console.print("[yellow]No traces found.[/]")
                return

            table = Table(title="Trace History")
            table.add_column("ID", style="cyan", max_width=30)
            table.add_column("Task")
            table.add_column("Model")
            table.add_column("Timestamp")
            table.add_column("Depth", justify="right")
            table.add_column("Tools", justify="right")
            table.add_column("Signature")

            for trace in traces:
                fp = db.get_fingerprint_by_trace(trace.id)
                table.add_row(
                    trace.id[:28] + "..." if len(trace.id) > 30 else trace.id,
                    trace.task_id,
                    trace.model,
                    trace.timestamp.strftime("%m-%d %H:%M"),
                    str(fp.depth) if fp else "-",
                    str(fp.tool_call_count) if fp else "-",
                    fp.signature_hash[:8] if fp else "-",
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("show")
def show_trace(
    trace_id: str = typer.Argument(..., help="Trace ID"),
    full: bool = typer.Option(False, "--full", "-f", help="Show full output"),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show details of a specific trace.

    Example:
        cogscope history show trace_abc123 --full
    """
    from cogscope.storage.database import get_database

    db = get_database()

    try:
        trace = db.get_trace(trace_id)
        fp = db.get_fingerprint_by_trace(trace_id)

        if json:
            data = {
                "trace": trace.model_dump(mode="json"),
                "fingerprint": fp.model_dump(mode="json") if fp else None,
            }
            print(json_lib.dumps(data, indent=2, default=str))
        else:
            output = (
                trace.output
                if full
                else (trace.output[:500] + "..." if len(trace.output) > 500 else trace.output)
            )

            console.print(
                Panel(
                    f"[bold]ID:[/] {trace.id}\n"
                    f"[bold]Task:[/] {trace.task_id}\n"
                    f"[bold]Model:[/] {trace.model}\n"
                    f"[bold]Adapter:[/] {trace.adapter_type}\n"
                    f"[bold]Timestamp:[/] {trace.timestamp}\n"
                    f"[bold]Latency:[/] {trace.latency_ms:.0f}ms\n"
                    f"[bold]Tokens:[/] {trace.token_usage.total_tokens}\n\n"
                    f"[bold]Prompt:[/]\n{trace.prompt[:200]}{'...' if len(trace.prompt) > 200 else ''}\n\n"
                    f"[bold]Output:[/]\n{output}",
                    title=f"[green]Trace: {trace_id[:30]}...[/]",
                )
            )

            if fp:
                console.print("\n[bold]Fingerprint:[/]")
                console.print(f"  Depth: {fp.depth}")
                console.print(f"  Steps: {fp.total_steps}")
                console.print(f"  Tools: {fp.tool_call_count}")
                console.print(f"  Tool sequence: {fp.tool_call_sequence}")
                console.print(f"  Corrections: {fp.correction_count}")
                console.print(f"  Uncertainty markers: {fp.uncertainty_markers}")
                console.print(f"  Verification steps: {fp.verification_steps}")
                console.print(f"  Hedging ratio: {fp.hedging_ratio:.2f}")
                console.print(f"  Signature: {fp.signature_hash}")

            if trace.tool_calls:
                console.print("\n[bold]Tool Calls:[/]")
                for tc in trace.tool_calls:
                    console.print(f"  - {tc.name}: {tc.arguments}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("tasks")
def list_tasks(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of tasks to show"),
) -> None:
    """List unique tasks with trace counts."""
    from cogscope.storage.database import get_database

    db = get_database()

    try:
        # Get task stats
        result = db.conn.execute(
            """
            SELECT task_id, COUNT(*) as count, MAX(timestamp) as last_trace
            FROM traces
            GROUP BY task_id
            ORDER BY last_trace DESC
            LIMIT ?
        """,
            [limit],
        ).fetchall()

        if not result:
            console.print("[yellow]No tasks found.[/]")
            return

        table = Table(title="Tasks")
        table.add_column("Task ID", style="cyan")
        table.add_column("Traces", justify="right")
        table.add_column("Last Activity")
        table.add_column("Baselines", justify="right")

        for row in result:
            task_id, count, last_trace = row
            baselines = db.get_baselines_for_task(task_id)

            table.add_row(
                task_id,
                str(count),
                str(last_trace)[:16] if last_trace else "-",
                str(len(baselines)),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("compare")
def compare_traces(
    trace_id_1: str = typer.Argument(..., help="First trace ID"),
    trace_id_2: str = typer.Argument(..., help="Second trace ID"),
) -> None:
    """Compare two traces side by side."""
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter
    from cogscope.storage.database import get_database

    db = get_database()
    engine = DiffEngine()
    formatter = DiffFormatter()

    try:
        fp1 = db.get_fingerprint_by_trace(trace_id_1)
        fp2 = db.get_fingerprint_by_trace(trace_id_2)

        if not fp1 or not fp2:
            console.print("[red]Fingerprints not found[/]")
            raise typer.Exit(1)

        diff = engine.diff(fp1, fp2)
        formatter.format_rich(diff)

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.callback()
def callback() -> None:
    """View trace history and details."""
    pass
