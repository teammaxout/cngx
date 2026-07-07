"""Rich live terminal dashboard for the Cogscope proxy."""

from __future__ import annotations

import time
from datetime import datetime

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cogscope.proxy.events import CaptureEvent, get_event_bus
from cogscope.tui.alerts import format_alert_panel, format_session_warning_panel


class LiveDashboard:
    def __init__(self, refresh_hz: float = 4.0):
        self.console = Console()
        self.bus = get_event_bus()
        self.refresh_interval = 1.0 / refresh_hz
        self.events: list[CaptureEvent] = []
        self.active_alert: CaptureEvent | None = None
        self.active_session_warning: CaptureEvent | None = None
        self.latest_session_id: str | None = None
        self.latest_session_turn: int = 0
        self.latest_session_health: str = "n/a"

    def _ingest(self) -> None:
        for ev in self.bus.drain(timeout=0.05):
            self.events.append(ev)
            if len(self.events) > 40:
                self.events = self.events[-40:]
            if ev.session_id:
                self.latest_session_id = ev.session_id
            if ev.session_turn is not None:
                self.latest_session_turn = ev.session_turn
            if ev.session_health:
                self.latest_session_health = ev.session_health
            if ev.session_stability_warning:
                self.active_session_warning = ev
            elif ev.alert and not ev.session_stability_warning:
                self.active_alert = ev

    def _health_style(self, health: str) -> str:
        if health == "varied":
            return "bold green"
        if health == "flattening":
            return "bold yellow"
        if health == "collapsed":
            return "bold red"
        if health == "warming up":
            return "dim"
        return "white"

    def _build_table(self) -> Table:
        table = Table(
            title="Recent calls",
            expand=True,
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column("Time", style="dim", width=8)
        table.add_column("Turn", justify="right", width=5)
        table.add_column("Model", width=12)
        table.add_column("Depth", justify="right", width=6)
        table.add_column("Verify", justify="right", width=7)
        table.add_column("Hedge", justify="right", width=7)
        table.add_column("Drift", justify="right", width=7)
        table.add_column("Status", width=14)

        for ev in reversed(self.events[-12:]):
            ts = ev.timestamp.strftime("%H:%M:%S")
            drift = "n/a" if ev.drift_score is None else f"{ev.drift_score:.0%}"
            turn = str(ev.session_turn) if ev.session_turn is not None else "n/a"
            if ev.session_stability_warning:
                status = Text("SESSION", style="bold yellow")
            elif ev.no_baseline:
                status = Text("no baseline", style="dim")
            elif ev.alert:
                status = Text("ALERT", style="bold red")
            else:
                status = Text("ok", style="green")
            table.add_row(
                ts,
                turn,
                ev.model[:12],
                str(ev.depth),
                str(ev.verification_steps),
                f"{ev.hedging_ratio:.2f}",
                drift,
                status,
            )
        return table

    def _build_session_panel(self) -> Panel:
        sid = self.latest_session_id or "n/a"
        short_sid = sid if len(sid) <= 24 else f"{sid[:21]}..."
        health_text = Text(
            self.latest_session_health, style=self._health_style(self.latest_session_health)
        )
        body = (
            f"[bold]Session[/] [dim]{short_sid}[/]\n"
            f"Turn [cyan]{self.latest_session_turn}[/] · "
            f"Verification trajectory: "
        )
        return Panel(
            Text.assemble(body, health_text),
            title="[bold]Session trajectory[/]",
            border_style="magenta",
            padding=(0, 1),
        )

    def _build_alert(self) -> Panel | Text:
        if self.active_session_warning:
            return Panel(
                format_session_warning_panel(self.active_session_warning),
                title="[bold yellow]Session stability warning[/]",
                border_style="yellow",
                padding=(1, 2),
            )
        if self.active_alert:
            return Panel(
                format_alert_panel(self.active_alert),
                title="[bold yellow]Drift alert[/]",
                border_style="red",
                padding=(1, 2),
            )
        return Text("Watching for structural drift and session collapse…", style="dim italic")

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="session", size=4),
            Layout(name="body", ratio=2),
            Layout(name="alert", size=8),
        )
        layout["header"].update(
            Panel(
                "[bold white]Cogscope[/] [dim]live watch[/]\n"
                "[green]●[/] Proxy capturing fingerprints alongside your traffic",
                border_style="cyan",
            )
        )
        layout["session"].update(self._build_session_panel())
        layout["body"].update(Panel(self._build_table(), border_style="blue"))
        layout["alert"].update(self._build_alert())
        return layout

    def run(self) -> None:
        with Live(self._render(), console=self.console, refresh_per_second=4) as live:
            try:
                while True:
                    self._ingest()
                    live.update(self._render())
                    time.sleep(self.refresh_interval)
            except KeyboardInterrupt:
                pass


def run_dashboard() -> None:
    LiveDashboard().run()
