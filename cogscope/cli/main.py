"""Main CLI entry point for Cogscope."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cogscope import __version__
from cogscope.cli import capture, demo, diff, drift, gate, history, pin

console = Console()


app = typer.Typer(
    name="cogscope",
    help="Cogscope, observe LLM reasoning, detect drift, check policies",
    add_completion=False,
    pretty_exceptions_enable=True,
    pretty_exceptions_short=True,
)

# Legacy / advanced command groups
app.add_typer(gate.app, name="gate", help="Policy checks (legacy commands)")
app.add_typer(demo.app, name="demo", help="System-level scenarios")
app.add_typer(capture.app, name="capture", help="Capture reasoning traces")
app.add_typer(diff.app, name="diff-advanced", help="Compare behaviors (advanced)")
app.add_typer(drift.app, name="drift", help="Drift analysis (advanced)")
app.add_typer(pin.app, name="pin-advanced", help="Baseline pinning (advanced)")
app.add_typer(history.app, name="history", help="View trace history")


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .cogscope"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults"),
) -> None:
    """Initialize Cogscope in the current directory."""
    cogscope_path = path / ".cogscope"

    if cogscope_path.exists() and not force:
        if yes:
            console.print("[green]Already initialized.[/] Use [cyan]--force[/] to reinitialize.")
            raise typer.Exit(0)
        console.print("[red]Already initialized. Use --force to reinitialize.[/]")
        raise typer.Exit(1)

    default_adapter = "mock"
    default_model = "mock-model"
    interactive = not yes and sys.stdin.isatty()
    if interactive:
        console.print(
            Panel(
                "[bold]Cogscope setup[/]\nQuick questions, or pass [cyan]--yes[/] to skip.",
                border_style="cyan",
            )
        )
        adapter_choice = typer.prompt(
            "Default provider for local capture (mock/openai/gemini/claude)",
            default="mock",
        )
        if adapter_choice in ("openai", "gemini", "claude", "mock"):
            default_adapter = adapter_choice
        if default_adapter == "openai":
            default_model = "gpt-4o-mini"
        elif default_adapter == "gemini":
            default_model = "gemini-2.5-flash"
        elif default_adapter == "claude":
            default_model = "claude-sonnet-4-20250514"

    cogscope_path.mkdir(parents=True, exist_ok=True)
    from cogscope.storage.database import Database

    db_path = cogscope_path / "cogscope.db"
    db = Database(db_path)
    db.close()

    config_path = cogscope_path / "config.json"
    config = {
        "version": __version__,
        "default_adapter": default_adapter,
        "default_model": default_model,
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    (cogscope_path / "contracts").mkdir(exist_ok=True)
    (cogscope_path / "reports").mkdir(exist_ok=True)

    console.print(
        Panel(
            f"[green]OK[/] Ready at {cogscope_path.resolve()}\n\n"
            "[bold]Try next:[/]\n"
            "  [cyan]cogscope quickstart[/]  30-second demo, no API keys\n"
            "  [cyan]cogscope watch[/]       local proxy + live dashboard\n"
            "  [cyan]cogscope pin --label baseline[/]  pin recent behavior",
            title="[bold]Cogscope[/]",
        )
    )


@app.command()
def quickstart() -> None:
    """Zero-config demo: catch a silent reasoning regression."""
    from cogscope.cli.quickstart_cmd import run_quickstart

    run_quickstart()


@app.command()
def watch(
    port: int = typer.Option(8642, "--port", "-p"),
    host: str = typer.Option("127.0.0.1", "--host"),
) -> None:
    """Start local proxy + live terminal dashboard."""
    from cogscope.cli.watch import run_watch

    run_watch(port=port, host=host)


@app.command()
def pin(
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Baseline name"),
    trace_id: Optional[str] = typer.Option(None, "--trace", help="Trace ID (default: latest)"),
) -> None:
    """Pin the latest capture as a named baseline."""
    from cogscope.storage.database import get_database
    from cogscope.versioning.pinning import PinningManager

    db = get_database()
    if trace_id is None:
        traces = db.get_recent_traces(limit=1)
        if not traces:
            console.print(
                "[red]No traces yet. Run [cyan]cogscope watch[/] or [cyan]cogscope capture[/] first.[/]"
            )
            raise typer.Exit(1)
        trace_id = traces[0].id

    name = label or f"baseline_{trace_id[-8:]}"
    manager = PinningManager(db)
    baseline = manager.pin(trace_id=trace_id, name=name)
    console.print(f"[green]OK[/] Pinned [bold]{baseline.name}[/] from trace {trace_id}")


@app.command()
def diff_cmd(
    baseline: Optional[str] = typer.Option(None, "--baseline", "-b", help="Baseline name"),
    limit: int = typer.Option(5, "--limit", "-n", help="Recent traces to compare"),
) -> None:
    """Compare recent traffic against a pinned baseline."""
    from cogscope.diff.engine import DiffEngine
    from cogscope.diff.formatter import DiffFormatter
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

    db = get_database()
    traces = db.get_recent_traces(limit=limit)
    if not traces:
        console.print("[yellow]No captures yet.[/]")
        raise typer.Exit(0)

    bm = BaselineManager(db)
    if baseline:
        baseline_fp = bm.get_fingerprint(baseline)
        console.print(f"\n[bold]Recent vs baseline: {baseline}[/]\n")
    else:
        baselines = bm.list()
        if not baselines:
            console.print("[yellow]No baseline pinned. Use [cyan]cogscope pin --label NAME[/][/]")
            raise typer.Exit(1)
        baseline = baselines[0].name
        baseline_fp = bm.get_fingerprint(baseline)
        console.print(f"\n[bold]Recent vs latest pin: {baseline}[/]\n")

    engine = DiffEngine()
    formatter = DiffFormatter()
    for trace in traces:
        fp = db.get_fingerprint_by_trace(trace.id)
        if not fp:
            continue
        d = engine.diff(baseline_fp, fp)
        console.print(f"[cyan]{trace.id}[/] ({trace.model}) drift {d.drift_score:.0%}")
        if d.drift_score > 0.2:
            formatter.format_rich(d)


# Register as `diff` without clashing with diff typer group, use callback
app.command("diff")(diff_cmd)


@app.command()
def check(
    prompt: str = typer.Argument(..., help="Prompt to check"),
    policy: Path = typer.Option(..., "--policy", "-c", help="Policy YAML"),
    model: str = typer.Option("mock-model", "--model", "-m"),
    adapter: str = typer.Option("mock", "--adapter", "-a"),
    task_id: str = typer.Option("policy_check", "--task", "-t"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Check a prompt against a behavior policy (CI-friendly exit codes)."""
    from cogscope.cli.check_cmd import run_check

    raise typer.Exit(run_check(prompt, policy, model, adapter, task_id, json_output))


@app.command()
def regression(
    suite: Path = typer.Option(..., "--suite", "-s", help="YAML benchmark suite"),
    policy: Path = typer.Option(..., "--policy", "-c", help="Policy YAML"),
    baseline_outcomes: Optional[Path] = typer.Option(
        None,
        "--baseline-outcomes",
        help="JSON file with baseline correct[] vector for McNemar test",
    ),
    model: str = typer.Option("mock-model", "--model", "-m"),
    adapter: str = typer.Option("mock", "--adapter", "-a"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Run fixed benchmark suite with McNemar or paired permutation tests (CI)."""
    from cogscope.cli.regression_cmd import run_regression_suite

    raise typer.Exit(
        run_regression_suite(suite, policy, model, adapter, baseline_outcomes, json_output)
    )


@app.command()
def report(
    hours: int = typer.Option(24, "--hours", "-h"),
    task_id: Optional[str] = typer.Option(None, "--task", "-t"),
    session: Optional[str] = typer.Option(
        None, "--session", "-s", help="Session trajectory report"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    baseline: Optional[str] = typer.Option(None, "--baseline", "-b"),
) -> None:
    """Shareable drift summary (terminal or HTML) or session trajectory report."""
    from cogscope.cli import report_cmd

    report_cmd.report(
        hours=hours, task_id=task_id, session=session, output=output, baseline=baseline
    )


@app.command()
def submit(
    baseline: str = typer.Option(..., "--baseline", "-b", help="Pinned baseline label"),
    task: Optional[str] = typer.Option(None, "--task", "-t", help="Filter by local task_id"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max recent fingerprints to submit"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only; do not send"),
) -> None:
    """Submit anonymized drift metrics to the public tracker (opt-in)."""
    from cogscope.cli.submit_cmd import run_submit

    raise typer.Exit(run_submit(baseline, task, limit, yes, dry_run))


@app.command()
def status() -> None:
    """Show Cogscope status and statistics."""
    from cogscope.core.config import get_config
    from cogscope.storage.database import get_database

    config = get_config()
    if not config.get_cogscope_path().exists():
        console.print("[yellow]Not initialized. Run [cyan]cogscope init[/].[/]")
        raise typer.Exit(1)

    db = get_database()
    stats = db.get_stats()
    table = Table(title="Cogscope", show_header=False)
    table.add_column("k", style="cyan")
    table.add_column("v", justify="right")
    table.add_row("Version", __version__)
    table.add_row("Traces", str(stats["traces"]))
    table.add_row("Fingerprints", str(stats["fingerprints"]))
    table.add_row("Baselines", str(stats["baselines"]))
    console.print(table)


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"Cogscope v{__version__}")


if __name__ == "__main__":
    app()
