"""cogscope quickstart — zero-key demo of catching silent regression."""

from __future__ import annotations

import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console(stderr=True)


def run_quickstart() -> None:
    """Run polished mock-adapter demo in under 30 seconds."""
    from cogscope.contracts import DeploymentGate
    from cogscope.core.models import BehavioralFingerprint, ReasoningTrace, TokenUsage
    from cogscope.system_demo.runner import run_without_cogscope
    from cogscope.system_demo.scenarios import MathTutoringScenario

    start = time.monotonic()
    scenario = MathTutoringScenario.get_scenario()
    scenario.pipeline_config.adapter = "mock"
    scenario.pipeline_config.model = "mock-model"

    console.print()
    console.print(
        Panel(
            "[bold white]Cogscope quickstart[/]\n\n"
            "No API keys. No setup. Watch what happens when model reasoning\n"
            "silently degrades — and how Cogscope catches it.",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    without = run_without_cogscope(scenario)

    console.print(Rule("[bold]Without Cogscope[/]", style="yellow"))
    console.print(
        f"  Pipeline completed: [green]yes[/]\n"
        f"  Downstream would run: [red bold]YES[/]\n"
        f"  Reasoning assumptions violated: "
        f"{'[red]yes[/]' if without.reasoning_assumptions_violated else '[green]no[/]'}"
    )
    if without.silent_failure_description:
        console.print(f"  [dim]{without.silent_failure_description}[/]")
    console.print()

    # Deterministic degraded fingerprint — correct answer, shallow reasoning
    shallow_trace = ReasoningTrace(
        id="quickstart_shallow",
        timestamp=datetime.utcnow(),
        task_id="math_tutoring",
        model="mock-model",
        adapter_type="mock",
        prompt=scenario.problem,
        output="The dimensions are 4 cm by 8 cm.",
        reasoning_content="The dimensions are 4 cm by 8 cm.",
        token_usage=TokenUsage(prompt_tokens=40, completion_tokens=12, total_tokens=52),
    )
    shallow_fp = BehavioralFingerprint(
        trace_id=shallow_trace.id,
        task_id="math_tutoring",
        timestamp=datetime.utcnow(),
        model="mock-model",
        depth=1,
        branching_factor=0.0,
        total_steps=1,
        max_step_length=40,
        tool_call_count=0,
        tool_call_sequence=[],
        tool_diversity=0.0,
        tool_success_rate=1.0,
        output_length=35,
        reasoning_length=35,
        compression_ratio=1.0,
        avg_sentence_length=8.0,
        correction_count=0,
        backtrack_count=0,
        revision_count=0,
        uncertainty_markers=0,
        confidence_markers=1,
        hedging_ratio=0.0,
        verification_steps=0,
        example_count=0,
        structured_output=False,
        tokens_per_step=12.0,
        reasoning_overhead=0.0,
    )

    gate = DeploymentGate()
    gate_result = gate.check(shallow_fp, scenario.contract, shallow_trace)
    blocked = gate_result.blocked

    console.print(Rule("[bold]With Cogscope[/]", style="green"))
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
            "[bold green]That's the core idea.[/]\n\n"
            "The model still gave a plausible answer — but skipped the reasoning\n"
            "steps your policy requires. Without Cogscope that ships silently.\n\n"
            "Next: [cyan]cogscope watch[/] to fingerprint live traffic,\n"
            "[cyan]cogscope pin --label baseline[/] to set normal behavior,\n"
            "and get alerted only on corroborated drift — not shorter answers alone.\n\n"
            f"[dim]Completed in {elapsed:.1f}s[/]",
            title="[bold]Next[/]",
            border_style="green",
        )
    )
