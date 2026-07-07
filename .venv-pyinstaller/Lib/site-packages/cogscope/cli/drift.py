"""Drift command for Cogscope CLI."""

import json as json_lib
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()
console = Console()


@app.command("detect")
def detect_drift(
    task_id: str = typer.Argument(..., help="Task ID to analyze"),
    baseline: Optional[str] = typer.Option(
        None, "--baseline", "-b", help="Baseline to compare against"
    ),
    window: int = typer.Option(24, "--window", "-w", help="Time window in hours"),
    json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Detect behavioral drift for a task.

    Example:
        cogscope drift detect math --baseline math_v1 --window 48
    """
    from cogscope.drift.detector import DriftDetector

    detector = DriftDetector()

    try:
        report = detector.detect_drift(
            task_id=task_id,
            baseline_name=baseline,
            window_hours=window,
        )

        if json:
            print(json_lib.dumps(report.model_dump(mode="json"), indent=2, default=str))
        else:
            # Determine status color
            if report.drift_score < 0.1:
                status = "[green]STABLE[/]"
            elif report.drift_score < 0.3:
                status = "[yellow]MINOR DRIFT[/]"
            elif report.drift_score < 0.5:
                status = "[orange1]MODERATE DRIFT[/]"
            else:
                status = "[red]SIGNIFICANT DRIFT[/]"

            console.print(
                Panel(
                    f"[bold]Task:[/] {task_id}\n"
                    f"[bold]Status:[/] {status}\n"
                    f"[bold]Drift Score:[/] {report.drift_score:.1%}\n"
                    f"[bold]Trend:[/] {report.drift_trend}\n"
                    f"[bold]Samples:[/] {report.sample_count}\n"
                    f"[bold]Window:[/] {window}h\n\n"
                    f"[bold]Summary:[/] {report.summary}",
                    title="[bold]Drift Detection Report[/]",
                )
            )

            if report.significant_changes:
                console.print("\n[bold]Significant Changes:[/]")
                table = Table(show_header=True)
                table.add_column("Metric")
                table.add_column("Baseline", justify="right")
                table.add_column("Current", justify="right")
                table.add_column("Significance")

                for change in report.significant_changes:
                    sig_value = (
                        change.significance.value
                        if hasattr(change.significance, "value")
                        else str(change.significance)
                    )
                    table.add_row(
                        change.metric,
                        f"{change.baseline_value:.2f}",
                        f"{change.current_value:.2f}",
                        sig_value,
                    )

                console.print(table)

            if report.z_scores:
                console.print("\n[bold]Z-Scores:[/]")
                for metric, score in sorted(report.z_scores.items(), key=lambda x: -x[1]):
                    bar_len = int(min(score, 1) * 20)
                    bar = "█" * bar_len + "░" * (20 - bar_len)
                    console.print(f"  {metric:20} [{bar}] {score:.2f}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command("watch")
def watch_drift(
    task_id: str = typer.Argument(..., help="Task ID to watch"),
    baseline: Optional[str] = typer.Option(None, "--baseline", "-b", help="Baseline"),
    interval: int = typer.Option(60, "--interval", "-i", help="Check interval in seconds"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Alert threshold"),
) -> None:
    """Watch for drift in real-time.

    Example:
        cogscope drift watch math --baseline math_v1 --threshold 0.5
    """
    import time

    from cogscope.drift.detector import DriftDetector

    detector = DriftDetector()

    console.print(f"[bold]Watching task '{task_id}' for drift...[/]")
    console.print(f"Baseline: {baseline or 'auto'}, Threshold: {threshold:.0%}")
    console.print("Press Ctrl+C to stop.\n")

    try:
        while True:
            report = detector.detect_drift(task_id, baseline, window_hours=1)

            timestamp = report.end_time.strftime("%H:%M:%S")

            if report.drift_score >= threshold:
                console.print(f"[red]🚨 {timestamp} DRIFT ALERT: {report.drift_score:.1%}[/]")
                console.print(f"   {report.summary}")
            elif report.drift_score >= threshold * 0.5:
                console.print(f"[yellow]⚠️  {timestamp} Warning: {report.drift_score:.1%}[/]")
            else:
                console.print(f"[green]✓  {timestamp} Stable: {report.drift_score:.1%}[/]")

            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/]")


@app.command("quick")
def quick_check(
    baseline_name: str = typer.Argument(..., help="Baseline name"),
    trace_id: str = typer.Argument(..., help="Trace ID to check"),
) -> None:
    """Quick drift check between baseline and trace.

    Example:
        cogscope drift quick math_v1 trace_abc123
    """
    from cogscope.drift.detector import DriftDetector
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

    db = get_database()
    baseline_manager = BaselineManager()
    detector = DriftDetector()

    try:
        baseline_fp = baseline_manager.get_fingerprint(baseline_name)
        current_fp = db.get_fingerprint_by_trace(trace_id)

        if not current_fp:
            console.print("[red]Fingerprint not found for trace[/]")
            raise typer.Exit(1)

        score, status = detector.quick_check(current_fp, baseline_fp)

        console.print(f"{status}")
        console.print(f"Drift score: {score:.1%}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.callback()
def callback() -> None:
    """Detect and monitor behavioral drift."""
    pass
