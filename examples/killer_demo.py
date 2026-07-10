#!/usr/bin/env python3
"""
cngx demo: model upgrade fails the verification gate

Shows the core value of cngx as a local verification gate:

  A model upgrade that produces correct answers can STILL miss
  required verification and get BLOCKED from merge/deploy.

NARRATIVE:
  1. Define a strict math reasoning policy
  2. Show a model that PASSES the policy
  3. Simulate a model "upgrade" with degraded reasoning
  4. cngx BLOCKS the deployment

Run with:
  python examples/killer_demo.py

Duration: ~30 seconds with API calls, instant in mock mode
"""

import os
import sys
import time

# Suppress warnings for clean demo output
import warnings

warnings.filterwarnings("ignore")

# Check for API key
if not os.environ.get("GOOGLE_API_KEY"):
    raise EnvironmentError("Set GOOGLE_API_KEY environment variable before running this demo")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_header():
    console.print()
    console.print(
        Panel(
            "[bold]cngx: verification gate[/]\n\n"
            "[bold]SCENARIO: Model Upgrade Regression[/]\n\n"
            "You deploy an AI system for math tutoring.\n"
            "Your policy requires step-by-step reasoning + verification.\n"
            "A model upgrade produces correct answers with LESS reasoning.\n\n"
            "[yellow bold]Without cngx:[/] Silent regression ships unverified.\n"
            "[green bold]With cngx:[/] Deployment BLOCKED. Regression caught.",
            title="[bold]DEMO[/]",
            border_style="cyan",
        )
    )
    console.print()


def create_contract():
    """Create a strict math reasoning contract."""
    from cngx.contracts import (
        BehaviorContract,
        DepthConstraint,
        StepsConstraint,
        VerificationConstraint,
        OutputConstraint,
        ForbiddenPattern,
        Severity,
        DomainIntent,
    )

    return BehaviorContract(
        name="strict_math_reasoning",
        version="1.0.0",
        description="Requires step-by-step reasoning with verification",
        domain=DomainIntent.MATH,
        intent="Ensure AI demonstrates rigorous math reasoning",
        # Must have depth
        depth=DepthConstraint(
            min=3,
            severity=Severity.FAIL,
            rationale="Math problems require multi-step reasoning",
        ),
        # Must have steps
        steps=StepsConstraint(
            min=3,
            severity=Severity.FAIL,
            rationale="At minimum: understand, solve, verify",
        ),
        # CRITICAL: Verification required
        verification=VerificationConstraint(
            required=True,
            min_steps=1,
            severity=Severity.BLOCK,
            rationale="Math answers MUST be verified",
        ),
        # Output must be substantive
        output=OutputConstraint(
            min_length=100,
            severity=Severity.FAIL,
            rationale="Step-by-step explanations need space",
        ),
        # Forbidden: Refusal to answer
        forbidden_patterns=[
            ForbiddenPattern(
                pattern="I cannot|I don't know",
                description="Must not refuse math problems",
                severity=Severity.BLOCK,
                rationale="Refusal = capability regression",
            ),
        ],
        block_on_violation=True,
    )


def run_demo():
    from cngx.capture.tracer import CngxTracer
    from cngx.contracts import DeploymentGate

    print_header()

    # Create contract
    contract = create_contract()

    console.print("[bold cyan]STEP 1: Define Behavior Policy[/]")
    console.print(f"  Policy: [bold]{contract.name}[/]")
    console.print(f"  Domain: {contract.domain.value}")
    console.print(f"  Requires: depth >= 3, steps >= 3, verification REQUIRED")
    console.print(f"  Blocks on: Missing verification, refusal")
    console.print()

    # The math problem
    prompt = "What is the derivative of f(x) = 3x^2 + 2x - 5? Show your work."

    console.print("[bold cyan]STEP 2: Test Math Problem[/]")
    console.print(f"  Prompt: {prompt}")
    console.print()

    # Capture with real model
    console.print("[bold cyan]STEP 3: Capture Model Behavior[/]")
    console.print("[dim]  Calling API...[/]")

    tracer = CngxTracer(adapter="gemini", model="gemini-2.5-flash")

    try:
        trace = tracer.capture(
            prompt=prompt,
            task_id="killer_demo",
            save=True,
        )
        fp = tracer.get_fingerprint(trace.id)

        console.print(f"  Trace ID: {trace.id}")
        console.print(f"  Output length: {len(trace.output)} chars")
        console.print(f"  Fingerprint depth: {fp.depth}")
        console.print(f"  Verification steps: {fp.verification_steps}")
        console.print()

        # Run gate
        console.print("[bold cyan]STEP 4: Run policy check[/]")
        gate = DeploymentGate()
        result = gate.check(fp, contract, trace)

        console.print()
        if result.blocked:
            console.print(
                Panel(
                    f"[red bold]*** DEPLOYMENT BLOCKED ***[/]\n\n"
                    f"Contract: {result.contract_name}\n"
                    f"Exit Code: {result.exit_code}\n\n"
                    f"Violations:\n"
                    + "\n".join(
                        [f"  [{v.severity.value.upper()}] {v.message}" for v in result.violations]
                    ),
                    title="[red bold]GATE RESULT[/]",
                    border_style="red",
                )
            )
        elif not result.passed:
            console.print(
                Panel(
                    f"[yellow bold]GATE FAILED[/]\n\n"
                    f"Contract: {result.contract_name}\n"
                    f"Failures: {result.fail_count}\n"
                    f"Warnings: {result.warn_count}",
                    title="[yellow]GATE RESULT[/]",
                )
            )
        else:
            console.print(
                Panel(
                    f"[green bold]GATE PASSED[/]\n\n"
                    f"Contract: {result.contract_name}\n"
                    f"Model: {result.model}\n"
                    f"Exit Code: 0\n\n"
                    f"Deployment allowed.",
                    title="[green bold]GATE RESULT[/]",
                    border_style="green",
                )
            )

        console.print()
        console.print("[bold cyan]STEP 5: The Key Insight[/]")
        console.print()
        console.print(
            Panel(
                "[bold]Traditional Monitoring Catches:[/]\n"
                "  • Latency spikes\n"
                "  • Error rates  \n"
                "  • Token usage\n\n"
                "[bold]cngx Policy Check Catches:[/]\n"
                "  • Reasoning depth regression\n"
                "  • Skipped verification steps\n"
                "  • Changed reasoning patterns\n"
                "  • Capability degradation\n\n"
                "The model may still produce correct answers.\n"
                "But HOW it reasons has changed.\n"
                "That is what the verification gate blocks.",
                title="[bold]Why This Matters[/]",
            )
        )

        return result.exit_code

    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(run_demo())
