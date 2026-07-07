"""Example: Basic Cogscope usage demonstrating the full workflow."""

from cogscope import (
    CogscopeTracer,
    FingerprintExtractor,
    DiffEngine,
    BaselineManager,
)


def main():
    """Demonstrate basic Cogscope workflow."""
    print("=" * 60)
    print("Cogscope — Behavioral Contract Enforcement Demo")
    print("=" * 60)

    # 1. Create tracer with mock adapter (no actual LLM calls)
    print("\n1. Creating tracer with mock adapter...")
    tracer = CogscopeTracer(adapter="mock", model="mock-model")

    # 2. Capture a reasoning trace
    print("\n2. Capturing a reasoning trace...")
    prompt = "Solve the equation: 2x + 5 = 13"
    task_id = "math_reasoning"

    trace = tracer.capture(
        prompt=prompt,
        task_id=task_id,
        system_message="You are a careful math tutor who shows your work step by step.",
    )

    print(f"   Trace ID: {trace.id}")
    print(f"   Model: {trace.model}")
    print(f"   Latency: {trace.latency_ms:.0f}ms")
    print(f"   Output preview: {trace.output[:100]}...")

    # 3. Get fingerprint
    print("\n3. Extracting behavioral fingerprint...")
    fp = tracer.get_fingerprint(trace.id)
    if fp:
        print(f"   Depth: {fp.depth}")
        print(f"   Total steps: {fp.total_steps}")
        print(f"   Tool calls: {fp.tool_call_count}")
        print(f"   Corrections: {fp.correction_count}")
        print(f"   Verification steps: {fp.verification_steps}")
        print(f"   Hedging ratio: {fp.hedging_ratio:.2f}")
        print(f"   Signature hash: {fp.signature_hash}")

    # 4. Pin as baseline
    print("\n4. Pinning trace as baseline...")
    baseline_manager = BaselineManager()
    baseline = baseline_manager.create(
        trace_id=trace.id,
        name="math_v1",
        description="Initial math reasoning baseline",
    )
    print(f"   Baseline created: {baseline.name}")

    # 5. Capture with different behavior (simulate model change)
    print("\n5. Simulating behavior change...")
    tracer.switch_adapter("mock", preset="verbose")  # More verbose behavior

    new_trace = tracer.capture(
        prompt=prompt,
        task_id=task_id,
    )

    new_fp = tracer.get_fingerprint(new_trace.id)
    if new_fp:
        print(f"   New trace depth: {new_fp.depth}")
        print(f"   New trace steps: {new_fp.total_steps}")

    # 6. Compute diff
    print("\n6. Computing behavioral diff...")
    diff_engine = DiffEngine()
    if fp and new_fp:
        diff = diff_engine.diff(fp, new_fp)

        print(f"   Drift score: {diff.drift_score:.1%}")
        print(f"   Significance: {diff.significance.value}")
        print(f"   Total changes: {diff.total_changes}")

        if diff.changes:
            print("\n   Changes:")
            for change in diff.changes[:5]:
                print(f"     - {change.metric}: {change.baseline_value} → {change.current_value}")

        if diff.summary:
            print(f"\n   Summary: {diff.summary}")

    # 7. Check against baseline
    print("\n7. Checking new trace against baseline...")
    comparison = baseline_manager.compare_to_current(
        baseline_name="math_v1",
        current_trace_id=new_trace.id,
    )
    print(f"   Drift from baseline: {comparison['drift_score']:.1%}")
    print(f"   Breaking changes: {comparison['breaking_changes']}")

    print("\n" + "=" * 60)
    print("Demo complete! Use 'cogscope' CLI for interactive usage.")
    print("=" * 60)


if __name__ == "__main__":
    main()
