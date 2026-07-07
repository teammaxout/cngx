"""Example: Running regression tests on model behavior using diff + baselines."""

from cogscope import CogscopeTracer
from cogscope.diff.engine import DiffEngine
from cogscope.versioning.baseline import BaselineManager


def run_regression_tests():
    """Demonstrate regression testing workflow without the archived eval module."""
    print("=" * 60)
    print("Cogscope - Regression Testing Demo")
    print("=" * 60)

    tracer = CogscopeTracer(adapter="mock", model="test-model")
    baseline_manager = BaselineManager()
    diff_engine = DiffEngine()

    print("\n1. Creating known-good baseline...")
    tracer.switch_adapter("mock", preset="default")

    trace = tracer.capture(
        prompt="Calculate the compound interest on $1000 at 5% for 3 years",
        task_id="finance_calc",
    )

    baseline = baseline_manager.create(
        trace_id=trace.id,
        name="finance_v1",
        description="Verified finance calculation baseline",
    )
    print(f"   Created baseline: {baseline.name}")

    fp = tracer.get_fingerprint(trace.id)
    if fp:
        print(f"   Baseline depth: {fp.depth}")
        print(f"   Baseline verification steps: {fp.verification_steps}")

    print("\n2. Running regression check (similar behavior)...")
    tracer.switch_adapter("mock", preset="default")
    trace2 = tracer.capture(
        prompt="Calculate the compound interest on $1000 at 5% for 3 years",
        task_id="finance_calc",
    )
    fp2 = tracer.get_fingerprint(trace2.id)
    baseline_fp = baseline_manager.get_fingerprint("finance_v1")
    diff_similar = diff_engine.diff(baseline_fp, fp2)
    print(f"   Drift: {diff_similar.drift_score:.1%}")
    print(f"   Regression: {diff_similar.has_regression}")

    print("\n3. Running regression check (degraded behavior - terse)...")
    tracer.switch_adapter("mock", preset="terse")
    trace3 = tracer.capture(
        prompt="Calculate the compound interest on $1000 at 5% for 3 years",
        task_id="finance_calc",
    )
    fp3 = tracer.get_fingerprint(trace3.id)
    diff_degraded = diff_engine.diff(baseline_fp, fp3)
    print(f"   Drift: {diff_degraded.drift_score:.1%}")
    print(f"   Regression: {diff_degraded.has_regression}")

    print("\n" + "=" * 60)
    print("Regression testing demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_regression_tests()
