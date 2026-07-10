# Drift Detection

!!! note "Advanced, experimental"
    Drift detection (`wrap`/`watch`/`pin`/`diff`) is an advanced, experimental feature for monitoring long agent sessions. It is not the headline. If you want to catch an agent that claims the tests pass when they do not, start with [`cngx verify`](../getting-started/quickstart.md).

Drift detection answers: **"Is this response unusually different from behavior I've already pinned as normal?"**

It does **not** answer: "Is this model worse than last month industry-wide?" or "Is GPT better than Claude?"

cngx distinguishes two kinds of drift:

| Type | What it measures | What it means |
|------|------------------|---------------|
| **Structural drift** | Heuristic fingerprint metrics (depth, verification, hedging, etc.) | The reasoning *shape* changed relative to your baseline. Often reflects provider system-prompt tuning or stylistic changes, **not** proof of capability loss. |
| **Semantic drift** | Optional local embedding distance (`--semantic`) | The *content* distribution shifted even when pattern counts look similar. |

**Treat any structural drift alert as "something changed, go look," not "the model got worse."**

cngx uses **different statistical methods for different situations**. They are not blended into one mechanism.

## Pin a baseline first

```bash
cngx watch          # capture traffic via proxy
cngx pin --label my-baseline
```

A baseline stores a reference fingerprint for a task/model pair in `.cngx/cngx.db`.

## Compare live traffic

```bash
cngx diff --baseline my-baseline
```

Or watch the live TUI during `cngx watch`, drift scores appear when a baseline is pinned.

## Live proxy path (streaming, no ground truth)

**Algorithms:** [KSWIN](https://doi.org/10.1109/ICDM.2018.00060) (Raab et al., 2020) on count/continuous metrics via [frouros](https://github.com/IFCA/frouros); [MDDM](https://doi.org/10.1109/ICDM.2018.00059) (Pesaranghader et al., 2018) in-house on ratio-like metrics (hedging ratio).

- One streaming detector per **(model, pinned baseline, metric)** for core fingerprint metrics.
- Each new proxied call updates its metric streams in **background analysis**, the streamed response is not blocked.
- A per-metric flag comes from KSWIN (empirical CDF comparison in a sliding window) or MDDM (weighted-window McDiarmid bound), not mean-only cumulative sums.
- **Structural drift alerts** still require corroboration: at least two metric streams must flag, including at least one non-length metric. Length-only shifts never alert alone.

Implementation: `cngx/drift/streaming.py`, wired from `cngx/proxy/analysis.py`.

## One-shot diff / check path (batch comparison)

**Procedure** (`cngx/drift/batch.py`):

1. Per-metric **Mann-Whitney U** test (non-parametric two-sample comparison).
2. **Benjamini-Hochberg** false discovery rate correction across simultaneous tests (Benjamini & Hochberg, 1995).
3. **Cauchy Combination Test** (Liu & Xie, 2020) combining BH-rejected raw p-values into one omnibus statistic. CCT remains valid under arbitrary unknown dependency between correlated heuristic metrics (unlike Fisher's method).
4. Per-metric p-values and Cohen's d effect sizes are reported alongside the global CCT p-value for interpretability.

Used by `cngx diff`, `cngx drift detect`, and population comparisons in `DriftDetector`.

## CI regression path (paired benchmarks with oracle)

**Binary outcomes:** McNemar's exact test (McNemar, 1947) via the [holdout](https://github.com/jordan-baillie/holdout) library.

**Continuous / graded scores:** Paired permutation (sign-flip) test via `holdout.paired_permutation_test`, following the generalization recommended in [Amazon Science LLM-Accuracy-Stats](https://github.com/amazon-science/LLM-Accuracy-Stats).

```bash
cngx regression --suite examples/regression_suite_real.yaml \
  --policy examples/contracts/strict_verification.yaml \
  --baseline-outcomes baseline_scores.json
```

Only applies when the same fixed benchmark items are run under baseline and current conditions with a correctness oracle.

## Optional semantic drift (`cngx watch --semantic`)

Requires `pip install cngx[semantic]`. Compares local sentence embeddings (all-MiniLM-L6-v2) between baseline text and current output using Jensen-Shannon distance. This is **semantic drift**, separate from structural fingerprint drift.

## Optional OpenTelemetry export (`cngx watch --otel`)

Requires `pip install cngx[otel]`. Emits GenAI semantic convention spans with `cngx.fingerprint.*` attributes to an OTLP HTTP endpoint (default `http://localhost:4318`). Off by default; DuckDB remains the primary store.

## When alerts fire (summary)

| Situation | Method | Alerts? |
|-----------|--------|---------|
| Shorter answer, quality metrics stable | KSWIN/MDDM streaming | No |
| Concise but within baseline distribution | Streaming + guards | No |
| Population window shift (diff) | Mann-Whitney + BH + CCT | Yes if omnibus significant |
| Fixed benchmark regression (binary) | McNemar exact | Yes if paired shift |
| Fixed benchmark regression (continuous) | Paired permutation | Yes if paired shift |
| Topical shift, heuristics stable | Semantic embedding (`--semantic`) | Semantic drift only |
