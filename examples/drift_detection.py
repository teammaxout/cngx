"""Example: Detecting behavioral drift over time."""

from datetime import datetime
from cogscope import CogscopeTracer, DriftDetector, BaselineManager
from cogscope.diff.formatter import DiffFormatter


def simulate_drift():
    """Simulate behavioral drift and demonstrate detection."""
    print("=" * 60)
    print("Cogscope — Drift Detection Demo")
    print("=" * 60)

    tracer = CogscopeTracer(adapter="mock", model="test-model")
    drift_detector = DriftDetector()
    baseline_manager = BaselineManager()

    # 1. Generate baseline behavior (confident, thorough)
    print("\n1. Generating baseline behavior (confident preset)...")
    tracer.switch_adapter("mock", preset="confident")

    for i in range(5):
        trace = tracer.capture(
            prompt=f"Analyze data point {i}",
            task_id="drift_demo",
        )
        print(f"   Captured: {trace.id[:20]}...")

    # Pin the first as baseline
    traces = tracer.db.get_traces_by_task("drift_demo", limit=5)
    baseline = baseline_manager.create(
        trace_id=traces[-1].id,
        name="drift_demo_baseline",
        description="Confident baseline",
    )
    print(f"\n   Pinned baseline: {baseline.name}")

    # 2. Simulate gradual drift (becoming more uncertain)
    print("\n2. Simulating behavioral drift (uncertain preset)...")
    tracer.switch_adapter("mock", preset="uncertain")

    for i in range(5):
        trace = tracer.capture(
            prompt=f"Analyze data point {i+5}",
            task_id="drift_demo",
        )
        print(f"   Captured: {trace.id[:20]}...")

    # 3. Detect drift
    print("\n3. Detecting drift...")
    baseline_fp = baseline_manager.get_fingerprint("drift_demo_baseline")
    latest_trace = tracer.db.get_traces_by_task("drift_demo", limit=1)[0]
    latest_fp = tracer.db.get_fingerprint_by_trace(latest_trace.id)

    if latest_fp:
        score, status = drift_detector.quick_check(latest_fp, baseline_fp)
        print(f"   {status}")
        print(f"   Drift score: {score:.1%}")

    # 4. Show detailed diff
    print("\n4. Detailed behavior diff:")
    from cogscope.diff.engine import DiffEngine

    diff_engine = DiffEngine()
    formatter = DiffFormatter()

    if baseline_fp and latest_fp:
        diff = diff_engine.diff(baseline_fp, latest_fp)
        print(formatter.format_plain(diff))

    print("\n" + "=" * 60)
    print("Drift detection demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    simulate_drift()
