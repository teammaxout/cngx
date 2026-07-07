"""Plain-language structural and semantic drift alert formatting."""

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
    "semantic_embedding": "embedding distribution",
}


def describe_shift(shift: dict) -> str:
    metric = _METRIC_LABELS.get(shift["metric"], shift["metric"].replace("_", " "))
    direction = shift["direction"]
    drift_type = shift.get("drift_type", "structural")
    prefix = "Semantic drift" if drift_type == "semantic" else "Structural drift"
    if "baseline_mean" in shift:
        typical = shift["baseline_mean"]
        current = shift["current_value"]
        if direction == "decreased":
            return (
                f"{prefix}: {metric} dropped from typical {typical:.1f} to {current:.1f}. "
                "This may reflect provider tuning, not capability loss."
            )
        return f"{prefix}: {metric} rose from typical {typical:.1f} to {current:.1f}"
    return f"{prefix}: {metric} ({direction})"


def format_alert_panel(event: CaptureEvent) -> str:
    lines = [
        "[bold yellow]Drift detected[/] (something changed, go look):",
        "[dim]Structural shifts often reflect provider system-prompt or style tuning, "
        "not proof the model got worse.[/]",
    ]
    for shift in event.metric_shifts:
        lines.append(f"  • {describe_shift(shift)}")
    if event.baseline_name:
        lines.append(f"\n[dim]Baseline: {event.baseline_name}[/]")
    return "\n".join(lines)


def format_session_warning_panel(event: CaptureEvent) -> str:
    lines = [
        "[bold yellow]Session stability warning[/] (trajectory pattern, not single-turn drift):",
        "[dim]Verification behavior flattened across recent turns. This may indicate "
        "hollow verbosity or a lost verification habit, not proof the agent failed.[/]",
    ]
    if event.session_warning_message:
        lines.append(f"  {event.session_warning_message}")
    if event.session_id:
        lines.append(f"\n[dim]Session: {event.session_id} · turn {event.session_turn}[/]")
    return "\n".join(lines)
