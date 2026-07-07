"""Formatter for behavior diffs - CLI and structured output."""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cogscope.core.models import BehaviorChange, BehaviorDiff, ChangeType, SignificanceLevel


class DiffFormatter:
    """Format behavior diffs for display.

    Supports:
    - Rich CLI output (with colors and tables)
    - Plain text
    - JSON/dict
    """

    def __init__(self):
        self.console = Console()

    def format_rich(self, diff: BehaviorDiff) -> None:
        """Print a rich-formatted diff to the console."""
        # Header
        self._print_header(diff)

        # Changes table
        if diff.changes:
            self._print_changes_table(diff.changes)

        # Summary
        self._print_summary(diff)

        # Recommendations
        if diff.recommendations:
            self._print_recommendations(diff.recommendations)

    def _print_header(self, diff: BehaviorDiff) -> None:
        """Print the diff header."""
        sig_colors = {
            SignificanceLevel.NONE: "green",
            SignificanceLevel.MINOR: "blue",
            SignificanceLevel.MODERATE: "yellow",
            SignificanceLevel.MAJOR: "orange1",
            SignificanceLevel.CRITICAL: "red",
        }

        color = sig_colors.get(diff.significance, "white")
        sig_text = (
            diff.significance.value.upper()
            if hasattr(diff.significance, "value")
            else str(diff.significance).upper()
        )

        title = f"[bold {color}]Behavior Diff - {sig_text}[/]"

        self.console.print()
        self.console.print(
            Panel(
                f"Baseline: {diff.baseline_id}\n"
                f"Current:  {diff.current_id}\n"
                f"Drift Score: [bold]{diff.drift_score:.1%}[/]",
                title=title,
            )
        )

    def _print_changes_table(self, changes: list[BehaviorChange]) -> None:
        """Print changes in a table."""
        table = Table(title="Changes", show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Baseline", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("Change", justify="center")
        table.add_column("Significance", justify="center")

        change_symbols = {
            ChangeType.ADDED: "[green]+[/]",
            ChangeType.REMOVED: "[red]-[/]",
            ChangeType.INCREASED: "[green]↑[/]",
            ChangeType.DECREASED: "[red]↓[/]",
            ChangeType.CHANGED: "[yellow]~[/]",
            ChangeType.UNCHANGED: "[dim]=[/]",
        }

        sig_colors = {
            SignificanceLevel.NONE: "dim",
            SignificanceLevel.MINOR: "blue",
            SignificanceLevel.MODERATE: "yellow",
            SignificanceLevel.MAJOR: "orange1",
            SignificanceLevel.CRITICAL: "red bold",
        }

        for change in changes:
            if change.change_type == ChangeType.UNCHANGED:
                continue

            symbol = change_symbols.get(change.change_type, "?")
            sig_color = sig_colors.get(change.significance, "white")
            sig_text = (
                change.significance.value
                if hasattr(change.significance, "value")
                else str(change.significance)
            )

            # Format values
            baseline_str = self._format_value(change.baseline_value)
            current_str = self._format_value(change.current_value)

            table.add_row(
                change.metric,
                baseline_str,
                current_str,
                symbol,
                f"[{sig_color}]{sig_text}[/]",
            )

        self.console.print(table)

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, float):
            return f"{value:.3f}"
        elif isinstance(value, list):
            if len(value) > 3:
                return f"[{', '.join(str(v) for v in value[:3])}, ...]"
            return str(value)
        elif isinstance(value, bool):
            return "✓" if value else "✗"
        return str(value)

    def _print_summary(self, diff: BehaviorDiff) -> None:
        """Print the summary."""
        self.console.print()
        self.console.print(f"[bold]Summary:[/] {diff.summary}")
        self.console.print(
            f"Total changes: {diff.total_changes}, Breaking: {diff.breaking_changes}"
        )

    def _print_recommendations(self, recommendations: list[str]) -> None:
        """Print recommendations."""
        self.console.print()
        self.console.print("[bold]Recommendations:[/]")
        for rec in recommendations:
            self.console.print(f"  {rec}")

    def format_plain(self, diff: BehaviorDiff) -> str:
        """Format diff as plain text."""
        lines = [
            "=" * 60,
            f"BEHAVIOR DIFF - {diff.significance.value.upper() if hasattr(diff.significance, 'value') else diff.significance}",
            "=" * 60,
            f"Baseline: {diff.baseline_id}",
            f"Current:  {diff.current_id}",
            f"Drift Score: {diff.drift_score:.1%}",
            "",
            "CHANGES:",
            "-" * 40,
        ]

        for change in diff.changes:
            if change.change_type == ChangeType.UNCHANGED:
                continue
            lines.append(change.description)

        lines.extend(
            [
                "",
                f"Summary: {diff.summary}",
                f"Total changes: {diff.total_changes}, Breaking: {diff.breaking_changes}",
            ]
        )

        if diff.recommendations:
            lines.append("")
            lines.append("RECOMMENDATIONS:")
            for rec in diff.recommendations:
                lines.append(f"  {rec}")

        return "\n".join(lines)

    def format_dict(self, diff: BehaviorDiff) -> dict[str, Any]:
        """Format diff as a dictionary."""
        return {
            "baseline_id": diff.baseline_id,
            "current_id": diff.current_id,
            "drift_score": diff.drift_score,
            "significance": (
                diff.significance.value
                if hasattr(diff.significance, "value")
                else str(diff.significance)
            ),
            "total_changes": diff.total_changes,
            "breaking_changes": diff.breaking_changes,
            "summary": diff.summary,
            "changes": [
                {
                    "metric": c.metric,
                    "baseline": c.baseline_value,
                    "current": c.current_value,
                    "type": (
                        c.change_type.value
                        if hasattr(c.change_type, "value")
                        else str(c.change_type)
                    ),
                    "significance": (
                        c.significance.value
                        if hasattr(c.significance, "value")
                        else str(c.significance)
                    ),
                    "description": c.description,
                }
                for c in diff.changes
                if c.change_type != ChangeType.UNCHANGED
            ],
            "recommendations": diff.recommendations,
        }

    def format_json(self, diff: BehaviorDiff) -> str:
        """Format diff as JSON string."""
        import json

        return json.dumps(self.format_dict(diff), indent=2)
