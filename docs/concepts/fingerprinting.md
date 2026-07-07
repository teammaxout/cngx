# How Fingerprinting Works

Every captured LLM response becomes a **behavioral fingerprint**: a set of numeric metrics describing *how* the model reasoned, independent of whether the final answer is correct.

## The pipeline

```
Prompt + response  →  ReasoningTrace  →  MetricsCalculator  →  BehavioralFingerprint
```

Implementation: `cogscope/fingerprint/metrics.py` (pattern counting) and `cogscope/fingerprint/extractor.py` (assembly into a fingerprint object).

## Metrics (honest description)

These are **heuristic and regex-based**, not semantic understanding. They count surface patterns in the model's output and reasoning text.

| Metric | What it approximates | How it's measured |
|--------|----------------------|-------------------|
| `depth` | Reasoning chain depth | Paragraph/section structure in reasoning text |
| `total_steps` | Number of distinct reasoning steps | Step labels, numbered lists, transitions |
| `verification_steps` | Self-check attempts | Regex: "let me verify", "double-check", "confirm", etc. |
| `hedging_ratio` | Uncertainty vs confidence | Count of uncertainty markers / (uncertainty + confidence markers) |
| `correction_count` | Self-corrections | "wait", "actually", "I was wrong", etc. |
| `uncertainty_markers` | Hedging phrases | "might", "possibly", "I think", etc. |
| `confidence_markers` | Assertive phrases | "clearly", "therefore", "the answer is", etc. |
| `branching_factor` | Alternative paths explored | Branching language patterns |
| `output_length` | Final answer size | Character count |
| `reasoning_length` | Reasoning text size | Character count |
| `tool_call_count` | Tool invocations | From trace metadata when tools are used |

Full field list: `BehavioralFingerprint` in `cogscope/core/models.py`.

!!! warning "What fingerprints are not"
    - Not a measure of factual correctness
    - Not proof the model "understood" anything
    - Not immune to prompt engineering that mimics verification phrases
    - Not comparable across models without a per-model baseline

## Why regex?

Regex is fast, deterministic, and runs locally on every response without extra API calls. The tradeoff is obvious: a model can write "let me verify" without actually verifying. Cogscope treats metrics as **signals**, not verdicts — especially for drift detection, which looks at *change* from your baseline, not absolute scores.

## Fingerprints are stored locally

Each fingerprint links to a trace ID in `.cogscope/cogscope.db` (DuckDB). Prompt and output text stay in the trace table locally; they are **never** included in `cogscope submit` payloads.

## Related

- [Drift Detection](drift.md) — when metric changes trigger alerts
- [Writing a Policy](policies.md) — hard constraints on metrics
