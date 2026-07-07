"""Regression suite check with McNemar paired significance (CI path)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from rich.console import Console

console = Console(stderr=True)


def run_regression_suite(
    suite_path: Path,
    policy: Path,
    model: str = "mock-model",
    adapter: str = "mock",
    baseline_outcomes_path: Optional[Path] = None,
    json_output: bool = False,
) -> int:
    """Run fixed benchmark items and apply McNemar's test vs baseline outcomes.

    Suite YAML format::

        items:
          - prompt: "What is 2+2?"
            expected_substrings: ["4"]
          - prompt: "..."
            forbidden_substrings: ["error"]
    """
    from cogscope.capture.tracer import CogscopeTracer
    from cogscope.cli.check_cmd import _load_policy
    from cogscope.contracts import DeploymentGate
    from cogscope.drift.paired import evaluate_item_correctness, mcnemar_test

    with open(suite_path, encoding="utf-8") as f:
        suite = yaml.safe_load(f)
    items: list[dict[str, Any]] = suite.get("items") or []
    if not items:
        console.print("[red]Suite has no items[/]")
        return 2

    behavior_policy = _load_policy(policy)
    tracer = CogscopeTracer(adapter=adapter, model=model)
    gate = DeploymentGate()

    current_correct: list[bool] = []
    for i, item in enumerate(items):
        prompt = item["prompt"]
        trace = tracer.capture(prompt=prompt, task_id=f"regression_{i}", save=False)
        fp = tracer.get_fingerprint(trace.id)
        if not fp:
            current_correct.append(False)
            continue
        result = gate.check(fp, behavior_policy, trace)
        oracle = evaluate_item_correctness(
            trace.output or "",
            expected_substrings=item.get("expected_substrings"),
            forbidden_substrings=item.get("forbidden_substrings"),
            policy_passed=result.passed and not result.blocked,
        )
        current_correct.append(oracle)

    baseline_correct: Optional[list[bool]] = None
    if baseline_outcomes_path:
        with open(baseline_outcomes_path, encoding="utf-8") as f:
            data = json.load(f)
        baseline_correct = [bool(x) for x in data["correct"]]
    else:
        # First run seeds baseline (no McNemar yet)
        console.print("[yellow]No --baseline-outcomes provided; recording current run only.[/]")
        if json_output:
            print(json.dumps({"correct": current_correct, "n": len(current_correct)}, indent=2))
        else:
            passed = sum(current_correct)
            console.print(f"Suite: {passed}/{len(current_correct)} items passed policy oracle.")
        return 0 if all(current_correct) else 1

    mcnemar = mcnemar_test(baseline_correct, current_correct)
    if json_output:
        print(
            json.dumps(
                {
                    "mcnemar_p": mcnemar.p_value,
                    "shift_detected": mcnemar.shift_detected,
                    "degradation_detected": mcnemar.degradation_detected,
                    "discordant_b": mcnemar.b_baseline_wrong_current_right,
                    "discordant_c": mcnemar.c_baseline_right_current_wrong,
                    "current_correct": current_correct,
                },
                indent=2,
            )
        )
    else:
        console.print(mcnemar.summary)
        console.print(f"Current suite pass rate: {sum(current_correct)}/{len(current_correct)}")

    if mcnemar.shift_detected:
        return 1
    return 0 if all(current_correct) else 2
