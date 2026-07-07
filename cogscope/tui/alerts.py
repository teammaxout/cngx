"""Plain-language drift alert formatting."""

from __future__ import annotations

from cogscope.proxy.events import CaptureEvent

_METRIC_LABELS = {
    "depth": "reasoning depth",
    "verification_steps": "verification steps",
    "correction_count": "self-corrections",
    "uncertainty_markers": "uncertainty markers",
    "total_steps": "reasoning steps",
    "output_length": "response length",
    "reasoning_length": "reasoning length",
    "hedging_ratio": "hedging",
    "compression_ratio": "compression ratio",
}


def describe_shift(shift: dict) -> str:
    metric = _METRIC_LABELS.get(shift["metric"], shift["metric"].replace("_", " "))
    direction = shift["direction"]
    typical = shift["baseline_mean"]
    current = shift["current_value"]
    if direction == "decreased":
        return (
            f"{metric} dropped from a typical {typical:.1f} to {current:.1f} "
            f"— this response skipped behavior it normally shows"
        )
    return f"{metric} rose from a typical {typical:.1f} to {current:.1f}"


def format_alert_panel(event: CaptureEvent) -> str:
    lines = ["[bold red]Drift detected[/] — corroborated metric shifts:"]
    for shift in event.metric_shifts:
        lines.append(f"  • {describe_shift(shift)}")
    if event.baseline_name:
        lines.append(f"\n[dim]Baseline: {event.baseline_name}[/]")
    return "\n".join(lines)
