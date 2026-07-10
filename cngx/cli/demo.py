"""cngx Demo CLI - System-level demonstration of behavioral contract enforcement.

This CLI provides commands to run the system-level demo that shows
cngx's value as critical infrastructure for AI systems.
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="demo",
    help="System-level demo showing cngx as behavioral contract enforcement",
)
console = Console()


@app.command("run")
def demo_run(
    scenario: str = typer.Option(
        "math", "--scenario", "-s", help="Scenario to run: math, code, research, or all"
    ),
    mode: str = typer.Option(
        "compare",
        "--mode",
        "-m",
        help="Mode: compare (both), without (no cngx), with (cngx only)",
    ),
    output: str = typer.Option("rich", "--output", "-o", help="Output format: rich, json, ci"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
) -> None:
    """Run the system-level demo.

    This demonstrates cngx's value as an behavioral contract enforcement by showing:

    1. WITHOUT cngx: Silent failure - pipeline completes but reasoning
       assumptions are violated, downstream systems execute unsafely.

    2. WITH cngx: Explicit blocking - contract violations are caught,
       deployment is blocked, downstream systems are protected.

    Example:
        cngx demo run                     # Run math scenario comparison
        cngx demo run -s all              # Run all scenarios
        cngx demo run -s code -m without  # Show silent failure in code review
    """
    from cngx.system_demo.runner import (
        run_comparison,
        run_with_cngx,
        run_without_cngx,
    )
    from cngx.system_demo.scenarios import (
        CodeReviewScenario,
        MathTutoringScenario,
        ResearchAnalysisScenario,
        get_all_scenarios,
    )

    # Get scenarios
    scenario_map = {
        "math": MathTutoringScenario.get_scenario(),
        "code": CodeReviewScenario.get_scenario(),
        "research": ResearchAnalysisScenario.get_scenario(),
    }

    if scenario == "all":
        scenarios = list(scenario_map.values())
    elif scenario in scenario_map:
        scenarios = [scenario_map[scenario]]
    else:
        console.print(f"[red]Unknown scenario: {scenario}[/]")
        console.print(f"Available: {', '.join(scenario_map.keys())}, all")
        raise typer.Exit(1)

    # Print header
    if output == "rich" and not quiet:
        console.print()
        console.print(
            Panel(
                "[bold red]cngx: AI BEHAVIOR FIREWALL[/]\n\n"
                "[bold]SYSTEM-LEVEL DEMONSTRATION[/]\n\n"
                "This demo shows cngx protecting AI systems from silent reasoning failures.\n"
                "Real AI systems trust LLM reasoning. When that reasoning degrades,\n"
                "traditional monitoring cannot detect it. cngx can.",
                title="[bold magenta]🛡️ DEMO[/]",
                border_style="red",
            )
        )
        console.print()

    all_results = []
    exit_code = 0

    for s in scenarios:
        if output == "rich" and not quiet:
            console.print(f"\n[bold cyan]Running scenario: {s.name}[/]")
            console.print(f"[dim]{s.description}[/]")
            console.print()

        if mode == "compare":
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                if output == "rich" and not quiet:
                    _task = progress.add_task("Running comparison...", total=None)

                comparison = run_comparison(s)
                all_results.append(comparison)

                # Determine exit code
                if comparison.with_cngx.cngx_blocked:
                    exit_code = max(exit_code, 1)

            if output == "rich":
                console.print(comparison.generate_report())
            elif output == "json":
                print(
                    json.dumps(
                        {
                            "scenario": s.name,
                            "without_cngx": comparison.without_cngx.to_summary(),
                            "with_cngx": comparison.with_cngx.to_summary(),
                            "analysis": {
                                "silent_failure_prevented": comparison.silent_failure_prevented,
                                "deployment_would_have_shipped": comparison.deployment_would_have_shipped,
                                "downstream_protected": comparison.downstream_protected,
                            },
                        },
                        indent=2,
                    )
                )
            elif output == "ci":
                print(f"SCENARIO: {s.name}")
                print(f"WITHOUT_CNGX_SAFE: {not comparison.without_cngx.silent_failure}")
                print(f"WITH_CNGX_BLOCKED: {comparison.with_cngx.cngx_blocked}")
                print(f"SILENT_FAILURE_PREVENTED: {comparison.silent_failure_prevented}")

        elif mode == "without":
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                if output == "rich" and not quiet:
                    progress.add_task("Running WITHOUT cngx...", total=None)

                result = run_without_cngx(s)
                all_results.append(result)

            if output == "rich":
                _print_without_cngx_result(result, s)
            elif output == "json":
                print(json.dumps(result.to_summary(), indent=2))

        elif mode == "with":
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                if output == "rich" and not quiet:
                    progress.add_task("Running WITH cngx...", total=None)

                result = run_with_cngx(s)
                all_results.append(result)

                if result.cngx_blocked:
                    exit_code = 1

            if output == "rich":
                _print_with_cngx_result(result, s)
            elif output == "json":
                print(json.dumps(result.to_summary(), indent=2))

    # Final summary
    if output == "rich" and not quiet:
        console.print()
        console.print(
            Panel(
                "[bold]KEY INSIGHT[/]\n\n"
                "Traditional monitoring (latency, errors, costs) cannot detect\n"
                "reasoning quality degradation. The AI still responds, still\n"
                "produces output, still looks 'healthy'.\n\n"
                "[bold red]But the reasoning has changed.[/]\n\n"
                "cngx enforces behavioral contracts that catch these changes\n"
                "BEFORE they reach downstream systems or production users.\n\n"
                "[green bold]This is the behavioral contract enforcement.[/]",
                title="[bold]Why cngx Matters[/]",
                border_style="blue",
            )
        )

    raise typer.Exit(exit_code)


def _print_without_cngx_result(result, scenario):
    """Print result from running WITHOUT cngx."""
    status_style = "red" if result.silent_failure else "green"
    status_text = "SILENT FAILURE OCCURRED" if result.silent_failure else "Safe (this time)"

    console.print(
        Panel(
            f"[bold]Mode:[/] WITHOUT cngx\n"
            f"[bold]Completed:[/] {result.pipeline_completed}\n"
            f"[bold]Assumptions Violated:[/] {result.reasoning_assumptions_violated}\n"
            f"[bold]Downstream Would Execute:[/] {result.downstream_would_execute}\n"
            f"[bold]Downstream Safe:[/] {result.downstream_is_safe}\n"
            f"\n[bold {status_style}]Status: {status_text}[/]"
            + (f"\n\n[dim]{result.silent_failure_description}[/]" if result.silent_failure else ""),
            title="[bold yellow]⚠️ WITHOUT cngx[/]",
            border_style="yellow",
        )
    )


def _print_with_cngx_result(result, scenario):
    """Print result from running WITH cngx."""
    if result.cngx_blocked:
        status_style = "red"
        status_text = "DEPLOYMENT BLOCKED"
        border = "red"
        icon = "🛑"
    else:
        status_style = "green"
        status_text = "DEPLOYMENT ALLOWED"
        border = "green"
        icon = "✓"

    violations_text = ""
    if result.gate_result and result.gate_result.violations:
        violations_text = "\n[bold]Violations:[/]\n" + "\n".join(
            [
                f"  [{v.severity.value.upper()}] {v.message}"
                for v in result.gate_result.violations[:5]
            ]
        )

    console.print(
        Panel(
            f"[bold]Mode:[/] WITH cngx\n"
            f"[bold]Completed:[/] {result.pipeline_completed}\n"
            f"[bold]cngx Blocked:[/] {result.cngx_blocked}\n"
            f"[bold]Downstream Would Execute:[/] {result.downstream_would_execute}\n"
            f"[bold]Exit Code:[/] {result.gate_result.exit_code if result.gate_result else 'N/A'}\n"
            f"\n[bold {status_style}]Status: {status_text}[/]"
            f"{violations_text}",
            title=f"[bold green]{icon} WITH cngx[/]",
            border_style=border,
        )
    )


@app.command("scenarios")
def list_scenarios() -> None:
    """List available demo scenarios."""
    from cngx.system_demo.scenarios import get_all_scenarios

    console.print()
    console.print("[bold]Available Demo Scenarios[/]")
    console.print()

    for s in get_all_scenarios():
        console.print(f"[bold cyan]{s.scenario_type.value}[/]: {s.name}")
        console.print(f"  [dim]{s.description}[/]")
        console.print(f"  Contract: {s.contract.name}")
        console.print(f"  Downstream: {s.downstream_consumer.name}")
        console.print()


@app.command("explain")
def explain() -> None:
    """Explain what the demo demonstrates."""
    console.print()
    console.print(
        Panel(
            "[bold]THE PROBLEM[/]\n\n"
            "Real AI systems don't just call an LLM and display the result.\n"
            "They use LLM reasoning as INPUT to downstream logic:\n\n"
            "  • Math tutoring: AI reasoning → student feedback system\n"
            "  • Code review: AI analysis → merge gate decision\n"
            "  • Research: AI conclusions → trading algorithms\n\n"
            "When you upgrade the model, or configurations drift,\n"
            "the LLM might produce CORRECT ANSWERS with WORSE REASONING.\n\n"
            "Traditional monitoring cannot detect this:\n"
            "  ✓ Latency looks fine\n"
            "  ✓ Error rates are low\n"
            "  ✓ Tokens look normal\n"
            "  ✗ But reasoning depth collapsed\n"
            "  ✗ Verification steps disappeared\n"
            "  ✗ Downstream assumptions violated\n\n"
            "[bold red]THIS IS A SILENT FAILURE.[/]\n\n"
            "The system appears healthy while producing unsafe outputs.",
            title="[bold red]Without cngx[/]",
            border_style="red",
        )
    )

    console.print()

    console.print(
        Panel(
            "[bold]THE SOLUTION[/]\n\n"
            "cngx acts as a FIREWALL between AI reasoning and downstream systems.\n\n"
            "[bold cyan]Behavior Contracts[/] define what valid reasoning looks like:\n"
            "  • Minimum reasoning depth\n"
            "  • Required verification steps\n"
            "  • Forbidden patterns (e.g., 'I cannot')\n"
            "  • Required patterns (e.g., numeric output for math)\n\n"
            "[bold cyan]Policy check[/] validates behavior before release:\n"
            "  • BLOCK severity → EXIT CODE 1 → Cannot deploy\n"
            "  • FAIL severity → EXIT CODE 2 → Review required\n"
            "  • WARN severity → EXIT CODE 0 → Logged but allowed\n\n"
            "[bold green]Result:[/]\n"
            "  • Silent failures become explicit failures\n"
            "  • Reasoning regressions are caught in CI/CD\n"
            "  • Downstream systems are protected\n"
            "  • Model upgrades are VALIDATED before shipping",
            title="[bold green]With cngx[/]",
            border_style="green",
        )
    )

    console.print()
    console.print("[dim]Run 'cngx demo run' to see this in action.[/]")


@app.command("quick")
def quick_demo() -> None:
    """Quick 30-second demo for presentations.

    Shows: Problem → cngx solution → Blocked deployment
    """
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import (
        BehaviorContract,
        DeploymentGate,
        DepthConstraint,
        Severity,
        VerificationConstraint,
    )

    console.print()
    console.print("[bold red]cngx: AI BEHAVIOR FIREWALL[/]")
    console.print("[dim]Quick demonstration (30 seconds)[/]")
    console.print()

    # Step 1: The problem
    console.print("[bold cyan]STEP 1: The Problem[/]")
    console.print("  You deploy an AI math tutor.")
    console.print("  It must show step-by-step reasoning.")
    console.print("  A model upgrade might give correct answers")
    console.print("  with LESS reasoning. Students learn wrong process.")
    console.print()
    time.sleep(1)

    # Step 2: The contract
    console.print("[bold cyan]STEP 2: Define Behavior Contract[/]")
    contract = BehaviorContract(
        name="math_tutor",
        depth=DepthConstraint(min=4, severity=Severity.BLOCK),
        verification=VerificationConstraint(required=True, severity=Severity.BLOCK),
    )
    console.print(f"  Contract: {contract.name}")
    console.print("  Requires: depth >= 4, verification required")
    console.print("  Blocks deployment on violation")
    console.print()
    time.sleep(1)

    # Step 3: Capture behavior
    console.print("[bold cyan]STEP 3: Capture AI Behavior[/]")
    console.print("  [dim]Calling API...[/]")

    tracer = CngxTracer(adapter="gemini", model="gemini-flash-latest")
    trace = tracer.capture(
        prompt="What is 15 + 27? Give a brief answer.",
        task_id="quick_demo",
        save=True,
    )
    fp = tracer.get_fingerprint(trace.id)

    console.print(f"  Captured: {trace.id}")
    console.print(f"  Depth: {fp.depth}")
    console.print(f"  Verification steps: {fp.verification_steps}")
    console.print()
    time.sleep(1)

    # Step 4: Gate check
    console.print("[bold cyan]STEP 4: Run policy check[/]")
    gate = DeploymentGate()
    result = gate.check(fp, contract, trace)

    if result.blocked:
        console.print(
            Panel(
                f"[red bold]*** DEPLOYMENT BLOCKED ***[/]\n\n"
                f"Exit Code: {result.exit_code}\n"
                f"Violations: {result.block_count}\n\n"
                + "\n".join([f"• {v.message}" for v in result.violations[:3]]),
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                f"[green bold]DEPLOYMENT ALLOWED[/]\n\nExit Code: {result.exit_code}",
                border_style="green",
            )
        )

    console.print()
    console.print("[bold]This is the behavioral contract enforcement.[/]")
    console.print("[dim]Model upgrades are validated before shipping.[/]")

    raise typer.Exit(result.exit_code)
