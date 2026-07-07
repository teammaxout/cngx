"""cogscope report, drift summary for sharing."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(stderr=True)
app = typer.Typer(help="Drift and capture reports")


@app.command()
def report(
    hours: int = typer.Option(24, "--hours", "-h", help="Time window"),
    task_id: Optional[str] = typer.Option(None, "--task", "-t"),
    session: Optional[str] = typer.Option(
        None, "--session", "-s", help="Session trajectory report"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="HTML output path"),
    baseline: Optional[str] = typer.Option(None, "--baseline", "-b"),
) -> None:
    """Render a shareable drift summary or session trajectory report."""
    from cogscope.drift.detector import DriftDetector
    from cogscope.drift.trajectory import detect_verification_collapse, verification_health_label
    from cogscope.storage.database import get_database
    from cogscope.versioning.baseline import BaselineManager

    db = get_database()

    if session:
        fps = db.get_fingerprints_by_session(session)
        if not fps:
            console.print(f"[red]No fingerprints found for session {session}[/]")
            raise typer.Exit(1)

        verification = [fp.verification_steps for fp in fps]
        corrections = [fp.correction_count for fp in fps]
        trajectory = detect_verification_collapse(verification, corrections)
        health = verification_health_label(verification)

        table = Table(title=f"Session {session}", show_header=True, header_style="bold cyan")
        table.add_column("Turn", justify="right")
        table.add_column("Time")
        table.add_column("Model")
        table.add_column("Verify", justify="right")
        table.add_column("Corr", justify="right")
        table.add_column("Depth", justify="right")

        for fp in fps:
            turn = fp.metadata.get("session_turn", "?")
            table.add_row(
                str(turn),
                fp.timestamp.strftime("%Y-%m-%d %H:%M"),
                fp.model,
                str(fp.verification_steps),
                str(fp.correction_count),
                str(fp.depth),
            )

        warning = "yes" if trajectory.collapse_detected else "no"
        console.print(
            Panel(
                f"[bold]Session:[/] {session}\n"
                f"[bold]Turns:[/] {len(fps)}\n"
                f"[bold]Verification health:[/] {health}\n"
                f"[bold]Stability warning:[/] {warning}\n"
                f"[dim]{trajectory.summary}[/]",
                title="Cogscope session report",
                border_style="magenta",
            )
        )
        console.print(table)

        if output:
            rows = "".join(
                f"<tr><td>{fp.metadata.get('session_turn','?')}</td>"
                f"<td>{fp.timestamp.isoformat()}</td><td>{fp.model}</td>"
                f"<td>{fp.verification_steps}</td><td>{fp.correction_count}</td>"
                f"<td>{fp.depth}</td></tr>"
                for fp in fps
            )
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Session {session}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f1419; color: #e7ecf3; }}
h1 {{ color: #c084fc; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #334; padding: 0.5rem 0.75rem; text-align: left; }}
th {{ background: #1a2332; color: #7dd3fc; }}
</style></head><body>
<h1>Session trajectory report</h1>
<p>Session: {session} · Turns: {len(fps)} · Health: {health} · Warning: {warning}</p>
<p>{trajectory.summary}</p>
<table><thead><tr><th>Turn</th><th>Time</th><th>Model</th><th>Verify</th><th>Corr</th><th>Depth</th></tr></thead>
<tbody>{rows}</tbody></table></body></html>"""
            output.write_text(html, encoding="utf-8")
            console.print(f"[green]Wrote {output}[/]")
        return

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    if task_id:
        fingerprints = [
            fp for fp in db.get_fingerprints_by_task(task_id, limit=200) if fp.timestamp >= cutoff
        ]
    else:
        fingerprints = []
        for t in db.get_recent_traces(limit=100):
            fp = db.get_fingerprint_by_trace(t.id)
            if fp and fp.timestamp >= cutoff:
                fingerprints.append(fp)

    table = Table(title=f"Captures (last {hours}h)", show_header=True, header_style="bold cyan")
    table.add_column("Time")
    table.add_column("Model")
    table.add_column("Task")
    table.add_column("Depth", justify="right")
    table.add_column("Verify", justify="right")
    table.add_column("Drift", justify="right")

    detector = DriftDetector(db=db)
    baseline_fp = None
    baseline_name = baseline
    if baseline:
        bm = BaselineManager(db)
        baseline_fp = bm.get_fingerprint(baseline)

    alert_count = 0
    rows_html = []
    for fp in sorted(fingerprints, key=lambda x: x.timestamp, reverse=True)[:30]:
        drift_str = "n/a"
        if baseline_fp:
            hist = db.get_fingerprints_by_task(fp.task_id, limit=30)
            assessment = detector.assess_against_pinned_baseline(
                fp, baseline_fp, hist, baseline_name=baseline_name, model_name=fp.model
            )
            drift_str = f"{assessment.drift_score:.0%}"
            if assessment.should_alert:
                alert_count += 1
        table.add_row(
            fp.timestamp.strftime("%Y-%m-%d %H:%M"),
            fp.model,
            fp.task_id,
            str(fp.depth),
            str(fp.verification_steps),
            drift_str,
        )
        rows_html.append(
            f"<tr><td>{fp.timestamp.isoformat()}</td><td>{fp.model}</td>"
            f"<td>{fp.task_id}</td><td>{fp.depth}</td>"
            f"<td>{fp.verification_steps}</td><td>{drift_str}</td></tr>"
        )

    console.print(
        Panel(
            f"[bold]Window:[/] last {hours} hours\n"
            f"[bold]Captures:[/] {len(fingerprints)}\n"
            f"[bold]Alerts:[/] {alert_count}",
            title="Cogscope report",
            border_style="blue",
        )
    )
    console.print(table)

    if output:
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Cogscope Report</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f1419; color: #e7ecf3; }}
h1 {{ color: #5eead4; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #334; padding: 0.5rem 0.75rem; text-align: left; }}
th {{ background: #1a2332; color: #7dd3fc; }}
tr:nth-child(even) {{ background: #151c28; }}
.meta {{ color: #94a3b8; margin-bottom: 1.5rem; }}
</style></head><body>
<h1>Cogscope drift report</h1>
<p class="meta">Window: {hours}h · Captures: {len(fingerprints)} · Alerts: {alert_count}</p>
<table><thead><tr><th>Time</th><th>Model</th><th>Task</th><th>Depth</th><th>Verify</th><th>Drift</th></tr></thead>
<tbody>{"".join(rows_html)}</tbody></table>
</body></html>"""
        output.write_text(html, encoding="utf-8")
        console.print(f"[green]Wrote {output}[/]")
