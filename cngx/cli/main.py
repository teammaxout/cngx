"""Main CLI entry point for cngx."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cngx import __version__
from cngx.cli import capture, demo, diff, drift, gate, history, pin
from cngx.cli.stdio import configure_cli_stdio

configure_cli_stdio()
console = Console()


app = typer.Typer(
    name="cngx",
    help=(
        "Catch AI coding agents that say the tests pass when they do not.\n\n"
        "cngx runs the checks your agent claimed it ran, compares the real result\n"
        "to what the agent said, and blocks the merge when they disagree.\n\n"
        "Start here:\n"
        "  cngx quickstart                          30s demo, no setup\n"
        "  cngx verify --output-file agent.md -- pytest\n\n"
        "Advanced: check (heuristic policy lint), wrap / watch / pin / diff (session drift)"
    ),
    add_completion=False,
    pretty_exceptions_enable=True,
    pretty_exceptions_short=True,
)

# Advanced / legacy command groups (prefer top-level check, wrap, watch, pin, diff)
app.add_typer(gate.app, name="gate", help="Legacy alias for policy checks (prefer: cngx check)")
app.add_typer(demo.app, name="demo", help="System-level scenarios")
app.add_typer(capture.app, name="capture", help="Capture reasoning traces")
app.add_typer(diff.app, name="diff-advanced", help="Compare behaviors (advanced)")
app.add_typer(drift.app, name="drift", help="Drift analysis (advanced)")
app.add_typer(pin.app, name="pin-advanced", help="Baseline pinning (advanced)")
app.add_typer(history.app, name="history", help="View trace history")


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Project directory"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing .cngx"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive defaults"),
) -> None:
    """Initialize cngx in the current directory."""
    cngx_path = path / ".cngx"

    if cngx_path.exists() and not force:
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
                "[bold]cngx setup[/]\nQuick questions, or pass [cyan]--yes[/] to skip.",
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
            default_model = "gemini-flash-latest"
        elif default_adapter == "claude":
            default_model = "claude-sonnet-4-20250514"

    cngx_path.mkdir(parents=True, exist_ok=True)
    from cngx.storage.database import Database

    db_path = cngx_path / "cngx.db"
    db = Database(db_path)
    db.close()

    config_path = cngx_path / "config.json"
    config = {
        "version": __version__,
        "default_adapter": default_adapter,
        "default_model": default_model,
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    (cngx_path / "contracts").mkdir(exist_ok=True)
    (cngx_path / "reports").mkdir(exist_ok=True)

    console.print(
        Panel(
            f"[green]OK[/] Ready at {cngx_path.resolve()}\n\n"
            "[bold]Try next:[/]\n"
            "  [cyan]cngx quickstart[/]  30-second demo, no API keys\n"
            "  [cyan]cngx verify --output-file agent.md -- pytest[/]  gate an agent claim\n"
            "  [dim]advanced:[/] [cyan]cngx wrap -- aider[/] / [cyan]cngx watch[/]  session drift",
            title="[bold]cngx[/]",
        )
    )


@app.command()
def quickstart() -> None:
    """Zero-key demo: catch an agent that claims the tests pass when they fail."""
    from cngx.cli.quickstart_cmd import run_quickstart

    run_quickstart()


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def verify(
    ctx: typer.Context,
    claim: Optional[str] = typer.Option(
        None, "--claim", "-C", help="Agent claim text (what it said it did)"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output-file", "-o", help="File with the agent message to read the claim from"
    ),
    stdin: bool = typer.Option(False, "--stdin", help="Read the agent claim from stdin"),
    evidence_file: Optional[Path] = typer.Option(
        None, "--evidence-file", "-e", help="Use an existing test log instead of running a command"
    ),
    require_claim: bool = typer.Option(
        False, "--require-claim", help="Also block if checks pass but the agent made no claim"
    ),
    timeout: float = typer.Option(600.0, "--timeout", help="Seconds before the command is killed"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Machine-readable output"),
) -> None:
    """Run what the agent claimed it ran, then compare claim to reality.

    Put the real verification command after a double dash:

      cngx verify --output-file agent.md -- pytest

    cngx runs the command, reads what the agent said, and BLOCKS (exit 1) when
    the agent claimed success but the checks actually fail, or when its reported
    counts do not match the real run. The verdict is bound to real command
    output, so it cannot be satisfied by prose alone.

    Exit codes: 0 verified, 1 blocked, 2 usage error.
    """
    from cngx.cli.verify_cmd import run_verify

    raise typer.Exit(
        run_verify(
            command=list(ctx.args),
            claim=claim,
            output_file=output_file,
            stdin=stdin,
            evidence_file=evidence_file,
            require_claim=require_claim,
            timeout=timeout,
            json_output=json_output,
        )
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def wrap(
    ctx: typer.Context,
    port: int = typer.Option(8642, "--port", "-p", help="Proxy port (default 8642)"),
    host: str = typer.Option("127.0.0.1", "--host", help="Proxy host (localhost only)"),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Session id for multi-turn tracking",
    ),
    no_start_proxy: bool = typer.Option(
        False,
        "--no-start-proxy",
        help="Require an already-running proxy",
    ),
) -> None:
    """Route an agent CLI through the local proxy. Gemini is not supported."""
    from cngx.cli.wrap import run_wrap_cli

    run_wrap_cli(
        ctx,
        port=port,
        host=host,
        session_id=session_id,
        no_start_proxy=no_start_proxy,
    )


@app.command()
def watch(
    port: int = typer.Option(8642, "--port", "-p", help="Local proxy port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (localhost only)"),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Explicit session id for multi-turn trajectory tracking",
    ),
    semantic: bool = typer.Option(
        False,
        "--semantic",
        help="Enable optional local embedding drift signal (requires cngx[semantic])",
    ),
    otel: bool = typer.Option(
        False,
        "--otel",
        help="Forward OTel GenAI spans with fingerprint attributes (requires cngx[otel])",
    ),
    otel_endpoint: str = typer.Option(
        "http://localhost:4318",
        "--otel-endpoint",
        help="OTLP HTTP endpoint when --otel is set",
    ),
) -> None:
    """Start local proxy + live terminal dashboard."""
    from cngx.cli.watch import run_watch

    run_watch(
        port=port,
        host=host,
        session_id=session_id,
        semantic=semantic,
        otel=otel,
        otel_endpoint=otel_endpoint,
    )


@app.command()
def pin(
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Baseline name"),
    trace_id: Optional[str] = typer.Option(None, "--trace", help="Trace ID (default: latest)"),
) -> None:
    """Pin the latest capture as a named baseline."""
    from cngx.storage.database import get_database
    from cngx.versioning.pinning import PinningManager

    db = get_database()
    if trace_id is None:
        traces = db.get_recent_traces(limit=1)
        if not traces:
            console.print(
                "[red]No traces yet. Run [cyan]cngx watch[/] or [cyan]cngx capture[/] first.[/]"
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
    from cngx.diff.engine import DiffEngine
    from cngx.diff.formatter import DiffFormatter
    from cngx.storage.database import get_database
    from cngx.versioning.baseline import BaselineManager

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
            console.print("[yellow]No baseline pinned. Use [cyan]cngx pin --label NAME[/][/]")
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
    prompt: Optional[str] = typer.Argument(
        None,
        help="Prompt or task description",
    ),
    policy: Path = typer.Option(..., "--policy", "-c", help="Policy YAML"),
    prompt_opt: Optional[str] = typer.Option(None, "--prompt", "-p"),
    prompt_file: Optional[Path] = typer.Option(
        None,
        "--prompt-file",
        help="Task prompt context file (stored on trace, not sent to any API)",
    ),
    output_file: Optional[Path] = typer.Option(
        None,
        "--output-file",
        help="Agent output file for offline gating (no LLM call)",
    ),
    stdin: bool = typer.Option(
        False,
        "--stdin",
        help="Read agent output from stdin for offline gating",
    ),
    evidence_file: Optional[Path] = typer.Option(
        None,
        "--evidence-file",
        help="CI/test log to cross-check (must contain e.g. 'N passed'); offline only",
    ),
    model: str = typer.Option("mock-model", "--model", "-m"),
    adapter: str = typer.Option("mock", "--adapter", "-a"),
    task_id: str = typer.Option("policy_check", "--task", "-t"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    """Check one response against policy, no baseline or session history required.

    Answers: did this model response actually perform the verification your policy
    requires (tests, repro steps, explicit checks)? CI-friendly exit codes.

    Pass --output-file or --stdin to gate existing agent output without calling a provider.
    Pass --evidence-file with a real pytest/CI log to raise the bar above narrative claims.

    For continued agent runs, use watch, pin, and diff to detect session-level drift.
    """
    from cngx.cli.check_cmd import run_policy_check

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
    from cngx.cli.regression_cmd import run_regression_suite

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
    from cngx.cli import report_cmd

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
    """Submit opt-in drift metrics to the community tracker."""
    from cngx.cli.submit_cmd import run_submit

    raise typer.Exit(run_submit(baseline, task, limit, yes, dry_run))


@app.command()
def status() -> None:
    """Show cngx status and statistics."""
    from cngx.core.config import get_config
    from cngx.storage.database import get_database

    config = get_config()
    if not config.get_cngx_path().exists():
        console.print("[yellow]Not initialized. Run [cyan]cngx init[/].[/]")
        raise typer.Exit(1)

    db = get_database()
    stats = db.get_stats()
    table = Table(title="cngx", show_header=False)
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
    console.print(f"cngx v{__version__}")


if __name__ == "__main__":
    app()
