"""Behavioral fingerprint extraction from reasoning traces."""

from datetime import datetime

from cogscope.core.exceptions import FingerprintError
from cogscope.core.models import BehavioralFingerprint, ReasoningTrace
from cogscope.fingerprint.metrics import MetricsCalculator
from cogscope.fingerprint.normalizer import FingerprintNormalizer


class FingerprintExtractor:
    """Extract behavioral fingerprints from reasoning traces.

    The fingerprint captures the "shape" of reasoning:
    - How deep does the model think?
    - Does it use tools? Which ones? In what order?
    - Does it self-correct or show uncertainty?
    - How verbose is it?
    - Does it verify its work?

    This is the core innovation of Cogscope — transforming raw traces
    into comparable, versionable behavioral signatures.
    """

    def __init__(self):
        self.metrics = MetricsCalculator()
        self.normalizer = FingerprintNormalizer()

    def extract(self, trace: ReasoningTrace) -> BehavioralFingerprint:
        """Extract a behavioral fingerprint from a reasoning trace.

        Args:
            trace: The reasoning trace to analyze

        Returns:
            A BehavioralFingerprint capturing the behavioral signature
        """
        try:
            # Calculate structural metrics
            depth = self.metrics.calculate_depth(trace)
            branching = self.metrics.calculate_branching_factor(trace)
            total_steps = depth  # For now, depth == steps

            # Calculate max step length
            if trace.reasoning_tokens:
                max_step_length = (
                    max(len(t) for t in trace.reasoning_tokens) if trace.reasoning_tokens else 0
                )
            else:
                max_step_length = len(trace.output) // max(1, depth)

            # Tool usage metrics
            tool_call_count = len(trace.tool_calls)
            tool_call_sequence = [tc.name for tc in trace.tool_calls]
            tool_diversity = self.metrics.calculate_tool_diversity(trace)

            # Calculate tool success rate
            if trace.tool_calls:
                successful = sum(1 for tc in trace.tool_calls if tc.result is not None)
                tool_success_rate = successful / len(trace.tool_calls)
            else:
                tool_success_rate = 1.0

            # Verbosity metrics
            output_length = len(trace.output)
            reasoning_length = len(trace.reasoning_content) if trace.reasoning_content else 0
            compression_ratio = self.metrics.calculate_compression_ratio(trace)
            avg_sentence_length = self.metrics.calculate_avg_sentence_length(trace)

            # Self-correction metrics
            correction_count = self.metrics.count_corrections(trace)
            backtrack_count = self.metrics.count_backtrack(trace)
            revision_count = self.metrics.count_revisions(trace)

            # Uncertainty metrics
            uncertainty_markers = self.metrics.count_uncertainty_markers(trace)
            confidence_markers = self.metrics.count_confidence_markers(trace)
            hedging_ratio = self.metrics.calculate_hedging_ratio(trace)

            # Quality metrics
            verification_steps = self.metrics.count_verification_steps(trace)
            example_count = self.metrics.count_examples(trace)
            structured_output = self.metrics.detect_structured_output(trace)

            # Token efficiency
            tokens_per_step = self.metrics.calculate_tokens_per_step(trace)
            reasoning_overhead = self.metrics.calculate_reasoning_overhead(trace)

            # Create fingerprint
            fingerprint = BehavioralFingerprint(
                trace_id=trace.id,
                task_id=trace.task_id,
                timestamp=datetime.utcnow(),
                # Structural
                depth=depth,
                branching_factor=branching,
                total_steps=total_steps,
                max_step_length=max_step_length,
                # Tool usage
                tool_call_count=tool_call_count,
                tool_call_sequence=tool_call_sequence,
                tool_diversity=tool_diversity,
                tool_success_rate=tool_success_rate,
                # Verbosity
                output_length=output_length,
                reasoning_length=reasoning_length,
                compression_ratio=compression_ratio,
                avg_sentence_length=avg_sentence_length,
                # Self-correction
                correction_count=correction_count,
                backtrack_count=backtrack_count,
                revision_count=revision_count,
                # Uncertainty
                uncertainty_markers=uncertainty_markers,
                confidence_markers=confidence_markers,
                hedging_ratio=hedging_ratio,
                # Quality
                verification_steps=verification_steps,
                example_count=example_count,
                structured_output=structured_output,
                # Efficiency
                tokens_per_step=tokens_per_step,
                reasoning_overhead=reasoning_overhead,
                # Metadata
                model=trace.model,
                metadata={
                    "adapter": trace.adapter_type,
                    "latency_ms": trace.latency_ms,
                    "token_usage": trace.token_usage.model_dump(),
                },
            )

            return fingerprint

        except Exception as e:
            raise FingerprintError(f"Failed to extract fingerprint: {e}")

    def compare(
        self,
        fp1: BehavioralFingerprint,
        fp2: BehavioralFingerprint,
    ) -> float:
        """Compare two fingerprints and return similarity score.

        Args:
            fp1: First fingerprint
            fp2: Second fingerprint

        Returns:
            Similarity score between 0 and 1
        """
        return self.normalizer.compute_similarity(fp1, fp2)

    def extract_batch(
        self,
        traces: list[ReasoningTrace],
        max_workers: int = 4,
    ) -> list[BehavioralFingerprint]:
        """Extract fingerprints from multiple traces with concurrency.

        Uses ThreadPoolExecutor for I/O-bound parallelism.
        Falls back to sequential extraction on errors.

        Args:
            traces: List of reasoning traces
            max_workers: Maximum concurrent extractions

        Returns:
            List of behavioral fingerprints
        """
        if len(traces) <= 2 or max_workers <= 1:
            return [self.extract(trace) for trace in traces]

        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[tuple[int, BehavioralFingerprint]] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(traces))) as pool:
            futures = {pool.submit(self.extract, t): i for i, t in enumerate(traces)}
            for future in as_completed(futures):
                idx = futures[future]
                results.append((idx, future.result()))

        results.sort(key=lambda x: x[0])
        return [fp for _, fp in results]
