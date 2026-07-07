"""Killer Demo: Model Upgrade Breaks Behavior Contract

This demo shows the core value proposition of Cogscope contracts:
A model upgrade that looks fine can silently violate behavioral contracts.

Scenario:
- Define a contract requiring detailed step-by-step reasoning
- Run same prompt on different models
- Show one passes, one fails
"""

import os
import sys
import time

# Set your API key via environment variable before running:
#   export GOOGLE_API_KEY="your-key-here"
if not os.environ.get("GOOGLE_API_KEY"):
    print("⚠️  GOOGLE_API_KEY not set. Set it via: export GOOGLE_API_KEY='your-key'")
    print("   Falling back to mock adapter for demo purposes.\n")

import warnings

warnings.filterwarnings("ignore")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cogscope import CogscopeTracer
from cogscope.contracts import BehaviorContract, ContractValidator
from cogscope.contracts.schema import (
    DepthConstraint,
    StepsConstraint,
    OutputConstraint,
    RequiredPattern,
    Severity,
)

console = Console()


def create_golden_contract():
    """Create a contract encoding expected 'golden' behavior."""
    return BehaviorContract(
        name="thorough_reasoning",
        version="1.0.0",
        description="Requires thorough step-by-step reasoning with clear structure",
        depth=DepthConstraint(min=3, severity=Severity.FAIL),
        steps=StepsConstraint(min=3, severity=Severity.FAIL),
        output=OutputConstraint(min_length=100, severity=Severity.FAIL),
        required_patterns=[
            RequiredPattern(
                pattern=r"(step|first|then|next|finally|therefore|thus|because)",
                description="Must use reasoning connectors",
                check_output=True,
                severity=Severity.FAIL,
            ),
        ],
    )


def run_demo():
    console.print(
        Panel(
            "[bold]KILLER DEMO: Model Upgrade Breaks Behavior Contract[/]\n\n"
            "Scenario:\n"
            "  - You encoded your model's expected reasoning in a contract\n"
            "  - A new model version is deployed\n"
            "  - The contract catches the silent regression\n",
            title="[bold magenta]Cogscope Behavior Contracts[/]",
        )
    )

    # Define the contract
    contract = create_golden_contract()

    console.print(f"\n[bold cyan]Contract: {contract.name}[/]")
    console.print(f"  Minimum depth: {contract.depth.min}")
    console.print(f"  Minimum steps: {contract.steps.min}")
    console.print(f"  Minimum output: {contract.output.min_length} chars")
    console.print(f"  Required patterns: reasoning connectors\n")

    # The prompt
    prompt = "What is the derivative of x^3 + 2x^2 - 5x + 3? Explain step by step."
    console.print(f"[bold]Prompt:[/] {prompt}\n")

    # Save contract to file
    contract.to_yaml("demo_contract.yaml")

    # Test with real model
    console.print("[dim]Capturing trace with gemini-2.5-flash...[/]")

    tracer = CogscopeTracer(adapter="gemini", model="gemini-2.5-flash")

    try:
        trace = tracer.capture(
            prompt=prompt,
            task_id="demo_math",
            save=True,
        )

        # Get fingerprint
        fp = tracer.get_fingerprint(trace.id)

        console.print(f"\n[bold]Captured Trace:[/] {trace.id}")
        console.print(f"  Output length: {len(trace.output)} chars")
        console.print(f"  Fingerprint depth: {fp.depth}")
        console.print(f"  Total steps: {fp.total_steps}")

        # Validate
        validator = ContractValidator()
        result = validator.validate(fp, contract, trace)

        console.print()
        if result.passed:
            console.print(
                Panel(
                    "[green bold]CONTRACT PASSED[/]\n\n"
                    f"The model's behavior complies with the contract.\n\n"
                    f"Output (first 300 chars):\n{trace.output[:300]}...",
                    title="[green]Validation Result[/]",
                )
            )
        else:
            # Build violation details
            violations_text = ""
            for v in result.violations:
                violations_text += f"  [{v.severity.value.upper()}] {v.constraint}\n"
                violations_text += f"      {v.message}\n"

            console.print(
                Panel(
                    f"[red bold]CONTRACT VIOLATED[/]\n\n"
                    f"The model's behavior violates the contract:\n\n"
                    f"{violations_text}\n"
                    f"[bold]This is the kind of silent regression that Cogscope catches.[/]",
                    title="[red]Validation Result[/]",
                )
            )

        # Show the key insight
        console.print(
            Panel(
                "[bold]Key Insight[/]\n\n"
                "Traditional monitoring catches:\n"
                "  - Latency spikes\n"
                "  - Error rates\n"
                "  - Cost increases\n\n"
                "Cogscope Behavior Contracts catch:\n"
                "  - Shallow reasoning (depth regression)\n"
                "  - Skipped verification steps\n"
                "  - Changed reasoning patterns\n"
                "  - Lost capabilities (tool usage, structure)\n\n"
                "[magenta bold]The model still 'works'. The answer may even be correct.[/]\n"
                "[magenta bold]But the REASONING BEHAVIOR has changed.[/]",
                title="[bold cyan]Why Contracts Matter[/]",
            )
        )

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
