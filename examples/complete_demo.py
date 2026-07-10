#!/usr/bin/env python3
"""
cngx Complete Product Demo, Zero API Keys Required

This script demonstrates every major cngx capability using the mock adapter.
Run it to see the full product in action:

    python3 examples/complete_demo.py

No API keys, no network access, no external dependencies beyond cngx core.
"""

import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def header(title: str, subtitle: str = ""):
    console.print()
    console.print(
        Panel(
            f"[bold cyan]{title}[/]\n[dim]{subtitle}[/]" if subtitle else f"[bold cyan]{title}[/]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def step(num: int, desc: str):
    console.print(f"\n  [bold yellow]Step {num}:[/] {desc}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Capture & Fingerprint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def demo_capture():
    header("Capture & Fingerprint", "Trace an LLM call and extract behavioral metrics")

    from cngx import CngxTracer

    tracer = CngxTracer(adapter="mock", model="mock-model")

    step(1, "Capture a reasoning trace")
    trace = tracer.capture(prompt="Solve 2x + 5 = 13", task_id="math_demo")
    console.print(f"    Trace ID: [green]{trace.id}[/]")
    console.print(f"    Output: [dim]{trace.output[:80]}...[/]")
    console.print(f"    Latency: {trace.latency_ms:.0f}ms")

    step(2, "Extract behavioral fingerprint")
    fp = tracer.get_fingerprint(trace.id)

    table = Table(title="Behavioral Fingerprint", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Reasoning Depth", str(fp.depth))
    table.add_row("Total Steps", str(fp.total_steps))
    table.add_row("Tool Calls", str(fp.tool_call_count))
    table.add_row("Verification Steps", str(fp.verification_steps))
    table.add_row("Hedging Ratio", f"{fp.hedging_ratio:.1%}")
    table.add_row("Compression Ratio", f"{fp.compression_ratio:.2f}")
    table.add_row("Output Length", str(fp.output_length))
    console.print(table)

    return trace, fp


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Behavior Contracts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def demo_contracts(trace, fp):
    header("Behavior Contracts", "Define and validate behavioral requirements")

    from cngx.contracts import BehaviorContract, ContractValidator
    from cngx.contracts.schema import DepthConstraint, StepsConstraint, Severity

    step(3, "Define a behavior contract")
    contract = BehaviorContract(
        name="math_solver",
        version="1.0",
        domain="math",
        depth=DepthConstraint(min=3, severity=Severity.BLOCK),
        steps=StepsConstraint(min=2, severity=Severity.FAIL),
    )
    console.print(f"    Contract: [green]{contract.name} v{contract.version}[/]")
    console.print(f"    Depth ≥ {contract.depth.min} (severity: {contract.depth.severity.value})")

    step(4, "Validate trace against contract")
    validator = ContractValidator()
    result = validator.validate(fp, contract, trace)

    status = "[green]PASSED ✓[/]" if result.passed else "[red]BLOCKED ✗[/]"
    console.print(f"    Result: {status}")
    console.print(f"    Violations: {len(result.violations)}")
    if result.violations:
        for v in result.violations:
            console.print(f"      [{v.severity.value}] {v.constraint}: {v.message}")

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Behavioral Drift Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def demo_drift():
    header("Drift Detection", "Detect when LLM behavior changes")

    from cngx import CngxTracer, DiffEngine

    tracer = CngxTracer(adapter="mock", model="mock-model")

    step(5, "Capture baseline behavior (default preset)")
    trace_v1 = tracer.capture(prompt="Explain quantum entanglement", task_id="physics")
    fp_v1 = tracer.get_fingerprint(trace_v1.id)

    step(6, "Simulate model update (switch to terse preset)")
    tracer_v2 = CngxTracer(adapter="mock", model="mock-model-v2", preset="terse")
    trace_v2 = tracer_v2.capture(prompt="Explain quantum entanglement", task_id="physics")
    fp_v2 = tracer_v2.get_fingerprint(trace_v2.id)

    step(7, "Compute behavioral diff")
    diff_engine = DiffEngine()
    diff = diff_engine.diff(fp_v1, fp_v2)

    table = Table(title="Behavioral Drift Report", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Change", justify="right")

    for change in diff.changes[:8]:
        # Skip non-numeric changes (like tool_call_sequence)
        try:
            bv = float(change.baseline_value)
            cv = float(change.current_value)
            delta = cv - bv
            sign = "+" if delta > 0 else ""
            color = "red" if abs(delta) > 1 else "yellow" if abs(delta) > 0.1 else "green"
            table.add_row(
                change.metric,
                f"{bv:.2f}",
                f"{cv:.2f}",
                f"[{color}]{sign}{delta:.2f}[/]",
            )
        except (TypeError, ValueError):
            table.add_row(
                change.metric,
                str(change.baseline_value)[:20],
                str(change.current_value)[:20],
                "[yellow]changed[/]",
            )
    console.print(table)
    console.print(f"    Drift Score: [bold]{diff.drift_score:.1%}[/]")
    console.print(f"    Significance: {diff.significance.value}")


# Enforcement Gate


def demo_enforcement():
    header("CI/CD Verification Gate", "Block merges that fail policy checks")

    from cngx.enforcement import EnforcementGate, EnforcementConfig

    step(8, "Run enforcement gate (PASS scenario)")
    gate = EnforcementGate(
        EnforcementConfig(
            mode="enforce",
            drift_threshold=0.3,
            accuracy_threshold=0.8,
        )
    )
    result_pass = gate.run(drift_score=0.05, benchmark_accuracy=0.95, stability_score=0.98)
    console.print(f"    Result: [green]PASS[/], Exit code {int(result_pass.exit_code)}")

    step(9, "Run enforcement gate (BLOCK scenario)")
    result_block = gate.run(drift_score=0.5, benchmark_accuracy=0.6, stability_score=0.4)
    status = "[red]BLOCKED[/]" if not result_block.passed else "[green]PASS[/]"
    console.print(f"    Result: {status}, Exit code {int(result_block.exit_code)}")
    for check in result_block.checks:
        icon = "✓" if check.passed else "✗"
        color = "green" if check.passed else "red"
        console.print(f"      [{color}]{icon}[/] {check.check_name}: {check.message}")


# GitHub Action Generation


def demo_github_actions():
    header("GitHub Action Generator", "Auto-generate CI/CD pipeline YAML")

    from cngx.enforcement import GitHubActionGenerator

    step(10, "Generate GitHub Actions workflow")
    yaml_content = GitHubActionGenerator.generate(
        contract_path="examples/contracts/math_reasoning.yaml",
        python_version="3.11",
        provider="gemini",
    )
    # Show first 15 lines
    lines = yaml_content.strip().split("\n")[:15]
    console.print(
        Panel(
            "\n".join(lines) + "\n...",
            title="Generated .github/workflows/cngx-gate.yml",
            border_style="green",
        )
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def main():
    console.print(
        Panel(
            "[bold white]cngx: local verification gate[/]\n"
            "[dim]Complete demo • Zero API keys required[/]\n\n"
            "[cyan]Fingerprints agent/LLM output, runs policy checks,[/]\n"
            "[cyan]and detects drift using the mock adapter (no network).[/]",
            border_style="bold blue",
            padding=(1, 3),
        )
    )

    start = time.time()
    sections = [
        ("Capture & Fingerprint", demo_capture),
        ("Behavior Contracts", None),
        ("Drift Detection", demo_drift),
        ("Verification Gate", demo_enforcement),
        ("GitHub Action Generator", demo_github_actions),
    ]

    trace, fp = demo_capture()
    demo_contracts(trace, fp)

    for name, func in sections[2:]:
        try:
            func()
        except Exception as e:
            console.print(f"  [red]Error in {name}: {e}[/]")

    elapsed = time.time() - start

    console.print()
    console.print(
        Panel(
            f"[bold green]✓ All {len(sections)} sections completed in {elapsed:.2f}s[/]\n\n"
            "[dim]What you just saw:[/]\n"
            "  1. Traced an LLM call and extracted behavioral metrics\n"
            "  2. Validated behavior against a YAML contract\n"
            "  3. Detected behavioral drift between model versions\n"
            "  4. Ran a CI/CD verification gate (PASS + BLOCK scenarios)\n"
            "  5. Auto-generated a GitHub Actions workflow\n\n"
            "[bold cyan]Next steps:[/]\n"
            "  • Set GOOGLE_API_KEY and re-run with --adapter gemini\n"
            "  • Write policies under examples/contracts/\n"
            "  • Add 'cngx check' to your CI/CD pipeline\n",
            title="Demo Complete",
            border_style="bold green",
            padding=(1, 3),
        )
    )


if __name__ == "__main__":
    main()
