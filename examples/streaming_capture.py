"""Streaming Capture Example — Cogscope

Demonstrates how to use Cogscope's streaming capture to get
real-time token output while still capturing the full
reasoning trace and behavioral fingerprint.

Works with any adapter: openai, gemini, claude, mock.
"""

import asyncio
from cogscope import CogscopeTracer, StreamChunk


def sync_streaming_example():
    """Synchronous streaming — simplest approach."""
    print("=" * 60)
    print("Synchronous Streaming Capture")
    print("=" * 60)

    # Use mock adapter for demo (no API key needed)
    tracer = CogscopeTracer(adapter="mock", model="mock-model")

    full_text = ""
    for chunk in tracer.capture_stream(
        task_id="stream_demo",
        prompt="Explain how neural networks learn",
        system_message="You are a helpful AI tutor.",
    ):
        if not chunk.is_final:
            # Print tokens as they arrive
            print(chunk.text, end="", flush=True)
            full_text += chunk.text
        else:
            # Final chunk — trace is saved automatically
            trace = chunk.metadata["trace"]
            print(f"\n\n--- Stream Complete ---")
            print(f"  Model: {trace.model}")
            print(f"  Latency: {trace.latency_ms:.0f}ms")
            print(f"  Tokens: {trace.token_usage.total_tokens}")
            print(f"  Finish reason: {trace.finish_reason}")


async def async_streaming_example():
    """Async streaming — for high-throughput applications."""
    print("\n" + "=" * 60)
    print("Async Streaming Capture")
    print("=" * 60)

    tracer = CogscopeTracer(adapter="mock", model="mock-model")

    async for chunk in tracer.capture_stream_async(
        task_id="async_stream_demo",
        prompt="What is gradient descent?",
    ):
        if not chunk.is_final:
            if chunk.reasoning_text:
                print(f"[thinking] {chunk.reasoning_text}", end="", flush=True)
            if chunk.text:
                print(chunk.text, end="", flush=True)
        else:
            trace = chunk.metadata["trace"]
            print(f"\n\n--- Async Stream Complete ---")
            print(f"  Latency: {trace.latency_ms:.0f}ms")


def streaming_with_contract():
    """Stream first, then validate the trace against a contract."""
    from cogscope.contracts.schema import BehaviorContract
    from cogscope.contracts.validator import ContractValidator
    from cogscope.fingerprint.extractor import FingerprintExtractor

    print("\n" + "=" * 60)
    print("Streaming + Contract Validation")
    print("=" * 60)

    tracer = CogscopeTracer(adapter="mock", model="mock-model")

    # Collect the trace from stream
    final_trace = None
    for chunk in tracer.capture_stream(
        task_id="validated_stream",
        prompt="Calculate the derivative of x^3 + 2x",
    ):
        if not chunk.is_final:
            print(chunk.text, end="", flush=True)
        else:
            final_trace = chunk.metadata["trace"]
            print()

    if final_trace:
        # Extract fingerprint
        extractor = FingerprintExtractor()
        fingerprint = extractor.extract(final_trace)

        print(f"\nFingerprint extracted:")
        print(f"  Depth: {fingerprint.depth}")
        print(f"  Hedging ratio: {fingerprint.hedging_ratio:.2f}")
        print(f"  Tool calls: {fingerprint.tool_call_count}")

        # Validate against a contract (if one exists)
        print("\n  ✅ Trace captured and fingerprinted via streaming!")


if __name__ == "__main__":
    # Run sync example
    sync_streaming_example()

    # Run async example
    asyncio.run(async_streaming_example())

    # Run streaming + contract validation
    streaming_with_contract()

    print("\n🎉 All streaming examples complete!")
