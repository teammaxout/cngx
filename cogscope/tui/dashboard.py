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
from cogscope.tui.alerts import format_alert_panel


class LiveDashboard:
    def __init__(self, refresh_hz: float = 4.0):
        self.console = Console()
        self.bus = get_event_bus()
        self.refresh_interval = 1.0 / refresh_hz
        self.events: list[CaptureEvent] = []
        self.active_alert: CaptureEvent | None = None

    def _ingest(self) -> None:
        for ev in self.bus.drain(timeout=0.05):
            self.events.append(ev)
            if len(self.events) > 40:
                self.events = self.events[-40:]
            if ev.alert:
                self.active_alert = ev

    def _build_table(self) -> Table:
        table = Table(
            title="Recent calls",
            expand=True,
            show_lines=False,
            header_style="bold cyan",
        )
        table.add_column("Time", style="dim", width=8)
        table.add_column("Model", width=14)
        table.add_column("Depth", justify="right", width=6)
        table.add_column("Verify", justify="right", width=7)
        table.add_column("Hedge", justify="right", width=7)
        table.add_column("Drift", justify="right", width=7)
        table.add_column("Status", width=12)

        for ev in reversed(self.events[-12:]):
            ts = ev.timestamp.strftime("%H:%M:%S")
            drift = "—" if ev.drift_score is None else f"{ev.drift_score:.0%}"
            if ev.no_baseline:
                status = Text("no baseline", style="dim")
            elif ev.alert:
                status = Text("ALERT", style="bold red")
            else:
                status = Text("ok", style="green")
            table.add_row(
                ts,
                ev.model[:14],
                str(ev.depth),
                str(ev.verification_steps),
                f"{ev.hedging_ratio:.2f}",
                drift,
                status,
            )
        return table

    def _build_alert(self) -> Panel | Text:
        if self.active_alert:
            return Panel(
                format_alert_panel(self.active_alert),
                title="[bold yellow]⚠ Drift alert[/]",
                border_style="red",
                padding=(1, 2),
            )
        return Text("Watching for corroborated drift…", style="dim italic")

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
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
