#!/usr/bin/env python3
"""
cngx SYSTEM-LEVEL DEMO: policy check and verification gate

This script demonstrates cngx's core value:

  WITHOUT cngx: AI reasoning can silently degrade while systems
               continue operating, leading to invisible failures.

  WITH cngx: A policy check catches missing verification and shallow
            reasoning BEFORE merge/deploy, blocking unsafe releases.

RUN THIS DEMO:
  python examples/system_demo.py

WHAT THIS SHOWS:
  1. A realistic multi-stage AI decision pipeline
  2. How downstream systems TRUST AI reasoning
  3. What happens when reasoning degrades (silent failure)
  4. How cngx turns silent failures into explicit blocks

DURATION: ~60 seconds with API calls

REQUIREMENTS:
  - GOOGLE_API_KEY environment variable set
  - pip install cngx[gemini]
"""

import os
import sys
import time
from datetime import datetime

# Suppress warnings for clean output
import warnings

warnings.filterwarnings("ignore")

# Ensure API key
if not os.environ.get("GOOGLE_API_KEY"):
    print("ERROR: Set GOOGLE_API_KEY environment variable")
    print("  export GOOGLE_API_KEY=your-key-here")
    sys.exit(1)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def print_title():
    """Print demo title."""
    console.print()
    console.print(
        Panel(
            "[bold]cngx: verification gate[/]\n\n"
            "[bold]SYSTEM-LEVEL DEMONSTRATION[/]\n\n"
            "Local CLI that fingerprints agent/LLM output and gates\n"
            "merges when required verification is missing.\n\n"
            "[yellow]The Problem:[/]\n"
            "  AI systems trust LLM reasoning for downstream decisions.\n"
            "  When reasoning quality degrades, failures are SILENT.\n"
            "  Traditional monitoring cannot detect reasoning regression.\n\n"
            "[green]The Solution:[/]\n"
            "  cngx runs a policy check that catches missing verification.\n"
            "  BLOCK severity violations prevent deployment (exit code 1).\n"
            "  Silent failures become explicit, preventable failures.",
            title="[bold]DEMO[/]",
            border_style="cyan",
            width=80,
        )
    )
    console.print()


def print_scenario_intro():
    """Print scenario introduction."""
    console.print("[bold cyan]━━━ SCENARIO: Math Tutoring System ━━━[/]")
    console.print()
    console.print("You're deploying an AI-powered math tutoring system.")
    console.print()
    console.print("[bold]System Architecture:[/]")
    console.print("  1. [cyan]Student Input[/] → Problem arrives")
    console.print("  2. [cyan]AI Reasoning[/] → LLM solves with explanation")
    console.print("  3. [cyan]Quality Check[/] → Verify reasoning quality")
    console.print("  4. [cyan]Student Feedback[/] → Downstream system acts on reasoning")
    console.print()
    console.print("[bold]The Policy (what we require):[/]")
    console.print("  • Reasoning depth ≥ 4 (multi-step explanation)")
    console.print("  • Verification required (must check work)")
    console.print("  • Clear result stated (no ambiguity)")
    console.print()
    console.print("[bold]The Problem:[/]")
    console.print('  "A rectangle has perimeter 24 cm. Length is twice width."')
    console.print('  "What are the dimensions? Show your work."')
    console.print()


def create_contract():
    """Create the behavior contract."""
    from cngx.contracts import (
        BehaviorContract,
        DepthConstraint,
        StepsConstraint,
        VerificationConstraint,
        OutputConstraint,
        ForbiddenPattern,
        RequiredPattern,
        Severity,
        DomainIntent,
    )

    return BehaviorContract(
        name="math_tutoring_contract",
        version="1.0.0",
        description="Ensures AI provides educational step-by-step math reasoning",
        domain=DomainIntent.MATH,
        intent="Protect students from shallow or incorrect math explanations",
        depth=DepthConstraint(
            min=4,
            severity=Severity.BLOCK,
            rationale="Math tutoring requires multi-step explanations. "
            "Shallow responses indicate the model is giving answers "
            "without teaching methodology. This harms student learning.",
        ),
        steps=StepsConstraint(
            min=3,
            severity=Severity.BLOCK,
            rationale="Educational math requires: understand problem, show work, "
            "verify answer. Less than 3 steps is pedagogically insufficient.",
        ),
        verification=VerificationConstraint(
            required=True,
            min_steps=1,
            severity=Severity.BLOCK,
            rationale="Math tutoring MUST verify answers. Teaching students to "
            "verify their work is fundamental to mathematical education.",
        ),
        output=OutputConstraint(
            min_length=150,
            severity=Severity.FAIL,
            rationale="Educational explanations require substantive content.",
        ),
        forbidden_patterns=[
            ForbiddenPattern(
                pattern=r"I cannot|I don't know how|I'm unable",
                description="Must not refuse math problems",
                severity=Severity.BLOCK,
                rationale="A math tutor refusing problems indicates capability regression.",
            ),
        ],
        required_patterns=[
            RequiredPattern(
                pattern=r"\d+",
                description="Math response must contain numbers",
                severity=Severity.FAIL,
                rationale="Mathematical tutoring without numbers is incomplete.",
            ),
        ],
        block_on_violation=True,
    )


def run_without_cngx_demo():
    """Run demo WITHOUT cngx protection."""
    from cngx.capture.tracer import CngxTracer

    console.print()
    console.print("[bold yellow]━━━ MODE: WITHOUT cngx ━━━[/]")
    console.print()
    console.print("[dim]This simulates what happens without a verification gate:[/]")
    console.print("[dim]  • AI produces output[/]")
    console.print("[dim]  • Downstream systems trust it[/]")
    console.print("[dim]  • No policy check[/]")
    console.print()

    # Capture with a brief prompt (simulating a model that gives short answers)
    tracer = CngxTracer(adapter="gemini", model="gemini-2.5-flash")

    # Use a prompt that encourages brief response
    problem = "A rectangle has perimeter 24 cm and length is twice width. What are the dimensions?"
    brief_prompt = f"{problem}\n\nGive the answer directly."

    console.print("[dim]Capturing AI reasoning...[/]")

    try:
        trace = tracer.capture(
            prompt=brief_prompt,
            task_id="without_cngx_demo",
            save=True,
        )
        fp = tracer.get_fingerprint(trace.id)

        console.print()
        console.print("[bold]AI Response Captured:[/]")
        console.print(f"  • Output length: {len(trace.output)} characters")
        console.print(f"  • Reasoning depth: {fp.depth}")
        console.print(f"  • Verification steps: {fp.verification_steps}")
        console.print()

        # Show the output (truncated)
        console.print("[bold]AI Output:[/]")
        output_preview = trace.output[:300] + "..." if len(trace.output) > 300 else trace.output
        console.print(Panel(output_preview, border_style="dim"))

        # Analyze silently
        assumptions_violated = []
        if fp.depth < 4:
            assumptions_violated.append(f"Reasoning depth {fp.depth} < 4 (required)")
        if fp.verification_steps == 0:
            assumptions_violated.append("No verification performed")

        console.print()
        if assumptions_violated:
            console.print("[bold red]SILENT FAILURE DETECTED[/]")
            console.print()
            console.print("Reasoning assumptions violated:")
            for v in assumptions_violated:
                console.print(f"  • {v}")
            console.print()
            console.print("[bold]But without cngx:[/]")
            console.print("  • Pipeline continues normally")
            console.print("  • Student receives this response")
            console.print("  • No alert, no block, no protection")
            console.print()
            console.print(
                Panel(
                    "[red]Downstream systems TRUST this reasoning.[/]\n"
                    "[red]Students learn from shallow explanations.[/]\n"
                    "[red]Educational quality silently degrades.[/]",
                    title="[red bold]RESULT: SILENT FAILURE[/]",
                    border_style="red",
                )
            )
            return True, trace, fp  # Silent failure occurred
        else:
            console.print("[green]Reasoning quality acceptable[/]")
            return False, trace, fp

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        return False, None, None


def run_with_cngx_demo():
    """Run demo WITH cngx protection."""
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    console.print()
    console.print("[bold green]━━━ MODE: WITH cngx ━━━[/]")
    console.print()
    console.print("[dim]Same scenario, but now with a cngx policy check:[/]")
    console.print("[dim]  • AI produces output[/]")
    console.print("[dim]  • cngx validates against policy[/]")
    console.print("[dim]  • BLOCK violations prevent deployment[/]")
    console.print()

    contract = create_contract()
    console.print(f"[bold]Policy:[/] {contract.name} v{contract.version}")
    console.print()

    tracer = CngxTracer(adapter="gemini", model="gemini-2.5-flash")

    # Same brief prompt
    problem = "A rectangle has perimeter 24 cm and length is twice width. What are the dimensions?"
    brief_prompt = f"{problem}\n\nGive the answer directly."

    console.print("[dim]Capturing AI reasoning...[/]")

    try:
        trace = tracer.capture(
            prompt=brief_prompt,
            task_id="with_cngx_demo",
            save=True,
        )
        fp = tracer.get_fingerprint(trace.id)

        console.print()
        console.print("[bold]AI Response Captured:[/]")
        console.print(f"  • Output length: {len(trace.output)} characters")
        console.print(f"  • Reasoning depth: {fp.depth}")
        console.print(f"  • Verification steps: {fp.verification_steps}")
        console.print()

        # Run cngx gate
        console.print("[bold]Running cngx policy check...[/]")
        console.print()

        gate = DeploymentGate()
        result = gate.check(fp, contract, trace)

        if result.blocked:
            console.print(
                Panel(
                    f"[red bold]*** DEPLOYMENT BLOCKED ***[/]\n\n"
                    f"Contract: {result.contract_name} v{result.contract_version}\n"
                    f"Exit Code: {result.exit_code}\n\n"
                    f"[bold]Violations:[/]\n"
                    + "\n".join(
                        [
                            (
                                f"  [{v.severity.value.upper()}] {v.message}\n"
                                f"        [dim]{v.rationale[:80]}...[/]"
                                if v.rationale
                                else f"  [{v.severity.value.upper()}] {v.message}"
                            )
                            for v in result.violations[:4]
                        ]
                    ),
                    title="[red bold]cngx GATE RESULT[/]",
                    border_style="red",
                )
            )
            console.print()
            console.print("[bold green]SILENT FAILURE PREVENTED[/]")
            console.print("  • Downstream systems protected")
            console.print("  • Students not exposed to shallow reasoning")
            console.print("  • CI/CD pipeline would fail (exit code 1)")
            return True, result  # Blocked
        else:
            console.print(
                Panel(
                    f"[green bold]DEPLOYMENT ALLOWED[/]\n\n"
                    f"Contract: {result.contract_name}\n"
                    f"Exit Code: {result.exit_code}",
                    title="[green]cngx GATE RESULT[/]",
                    border_style="green",
                )
            )
            return False, result

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        return False, None


def print_conclusion(without_cngx_failure: bool, cngx_blocked: bool):
    """Print demo conclusion."""
    console.print()
    console.print("[bold cyan]━━━ CONCLUSION ━━━[/]")
    console.print()

    table = Table(title="Demo Results", show_header=True)
    table.add_column("Mode", style="bold")
    table.add_column("Outcome", style="bold")
    table.add_column("Result")

    table.add_row(
        "WITHOUT cngx",
        "Silent Failure" if without_cngx_failure else "OK",
        "[red]Degraded reasoning shipped[/]" if without_cngx_failure else "[green]OK[/]",
    )
    table.add_row(
        "WITH cngx",
        "BLOCKED" if cngx_blocked else "Allowed",
        "[green]Regression caught[/]" if cngx_blocked else "[yellow]Allowed[/]",
    )

    console.print(table)
    console.print()

    if without_cngx_failure and cngx_blocked:
        console.print(
            Panel(
                "[bold green]cngx TURNED A SILENT FAILURE INTO AN EXPLICIT BLOCK[/]\n\n"
                "Without cngx:\n"
                "  • Reasoning quality degraded silently\n"
                "  • Downstream systems continued operating\n"
                "  • Users received substandard output\n"
                "  • Problem only discovered later (if ever)\n\n"
                "With cngx:\n"
                "  • Policy violation detected immediately\n"
                "  • Deployment blocked (exit code 1)\n"
                "  • CI/CD pipeline fails before production\n"
                "  • Engineers notified, problem fixed\n\n"
                "[bold]This is a verification gate.[/]",
                title="[bold]KEY INSIGHT[/]",
                border_style="green",
            )
        )

    console.print()
    console.print("[bold]Next Steps:[/]")
    console.print("  • [cyan]cngx check[/] - Test prompts or agent output against policies")
    console.print("  • [cyan]cngx check --json[/] - CI-friendly JSON + exit codes")
    console.print("  • [cyan]cngx demo explain[/] - Deeper explanation of concepts")
    console.print()


def main():
    """Main demo entry point."""
    start_time = time.time()

    print_title()
    print_scenario_intro()

    # Run WITHOUT cngx
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running WITHOUT cngx...", total=None)
        without_failure, trace1, fp1 = run_without_cngx_demo()

    time.sleep(1)

    # Run WITH cngx
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running WITH cngx...", total=None)
        cngx_blocked, result = run_with_cngx_demo()

    # Conclusion
    print_conclusion(without_failure, cngx_blocked)

    duration = time.time() - start_time
    console.print(f"[dim]Demo completed in {duration:.1f} seconds[/]")
    console.print()

    # Exit with appropriate code
    if cngx_blocked:
        sys.exit(1)  # Demonstrate that cngx would block deployment
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
