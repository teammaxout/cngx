"""cngx quickstart, zero-key demo of catching verification collapse."""

from __future__ import annotations

import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console(stderr=True)


def run_quickstart() -> None:
    """Run polished mock-adapter demo in under 30 seconds."""
    from cngx.contracts import DeploymentGate
    from cngx.core.models import BehavioralFingerprint, ReasoningTrace, TokenUsage
    from cngx.system_demo.runner import run_without_cngx
    from cngx.system_demo.scenarios import CodingAgentFixScenario

    start = time.monotonic()
    scenario = CodingAgentFixScenario.get_scenario()
    scenario.pipeline_config.adapter = "mock"
    scenario.pipeline_config.model = "mock-model"

    console.print()
    console.print(
        Panel(
            "[bold white]cngx quickstart[/]\n\n"
            "No API keys. No setup. A coding agent returns a plausible patch\n"
            "but skips the test run your policy requires. Watch cngx block it\n"
            "on message one, before auto-merge would ship it.",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    without = run_without_cngx(scenario)

    console.print(Rule("[bold]Without cngx[/]", style="yellow"))
    console.print(
        f"  Pipeline completed: [green]yes[/]\n"
        f"  Auto-merge would run: [red bold]YES[/]\n"
        f"  Verification assumptions violated: "
        f"{'[red]yes[/]' if without.reasoning_assumptions_violated else '[green]no[/]'}"
    )
    if without.silent_failure_description:
        console.print(f"  [dim]{without.silent_failure_description}[/]")
    console.print()

    # Deterministic degraded fingerprint: plausible patch, zero verification steps
    shallow_trace = ReasoningTrace(
        id="quickstart_shallow",
        timestamp=datetime.utcnow(),
        task_id="coding_agent_fix",
        model="mock-model",
        adapter_type="mock",
        prompt=scenario.problem,
        output=(
            "Patch: use items[(page - 1) * size : page * size] for 1-based pages. "
            "Ready to merge."
        ),
        reasoning_content=(
            "The slice offset is wrong for page 1. Adjust indices and merge."
        ),
        token_usage=TokenUsage(prompt_tokens=48, completion_tokens=18, total_tokens=66),
    )
    shallow_fp = BehavioralFingerprint(
        trace_id=shallow_trace.id,
        task_id="coding_agent_fix",
        timestamp=datetime.utcnow(),
        model="mock-model",
        depth=1,
        branching_factor=0.0,
        total_steps=1,
        max_step_length=80,
        tool_call_count=0,
        tool_call_sequence=[],
        tool_diversity=0.0,
        tool_success_rate=1.0,
        output_length=90,
        reasoning_length=55,
        compression_ratio=1.0,
        avg_sentence_length=12.0,
        correction_count=0,
        backtrack_count=0,
        revision_count=0,
        uncertainty_markers=0,
        confidence_markers=1,
        hedging_ratio=0.0,
        verification_steps=0,
        example_count=0,
        structured_output=False,
        tokens_per_step=18.0,
        reasoning_overhead=0.0,
    )

    gate = DeploymentGate()
    gate_result = gate.check(shallow_fp, scenario.contract, shallow_trace)
    blocked = gate_result.blocked

    console.print(Rule("[bold]With cngx[/]", style="green"))
    icon = "[red bold]BLOCKED[/]" if blocked else "[yellow]review[/]"
    console.print(f"  Policy check: {icon}")
    if gate_result.violations:
        console.print("  [bold]Why:[/]")
        for v in gate_result.violations[:4]:
            console.print(f"    • [{v.severity.value}] {v.message}")
    console.print()

    elapsed = time.monotonic() - start
    console.print(
        Panel(
            "[bold green]That's the headline check.[/]\n\n"
            "The agent's answer looks merge-ready, but it never ran tests.\n"
            "cngx check catches that on the first response, no baseline needed.\n\n"
            "For long agent sessions, keep the proxy running:\n"
            "[cyan]cngx watch[/] fingerprints live traffic,\n"
            "[cyan]cngx pin --label baseline[/] sets normal behavior,\n"
            "and drift alerts fire only on corroborated collapse, not shorter replies.\n\n"
            f"[dim]Completed in {elapsed:.1f}s[/]",
            title="[bold]Next[/]",
            border_style="green",
        )
    )
