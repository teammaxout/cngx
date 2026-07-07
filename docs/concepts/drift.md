# Drift Detection

Drift detection answers: **"Is this response unusually different from behavior I've already pinned as normal?"**

It does **not** answer: "Is this model worse than last month industry-wide?" or "Is GPT better than Claude?"

## Pin a baseline first

```bash
cogscope watch          # capture traffic via proxy
cogscope pin --label my-baseline
```

A baseline stores a reference fingerprint for a task/model pair in `.cogscope/cogscope.db`.

## Compare live traffic

```bash
cogscope diff --baseline my-baseline
```

Or watch the live TUI during `cogscope watch` — drift scores appear when a baseline is pinned.

## When alerts fire (design principle)

Implemented in `cogscope/drift/detector.py` and `cogscope/calibration/profiles.py`:

1. **Relative to your baseline history** — not hardcoded universal thresholds.
2. **Multi-metric corroboration** — at least two metrics must be statistical outliers, including at least one *quality* metric (`verification_steps`, `depth`, `correction_count`, etc.).
3. **Length alone never alerts** — a shorter, more efficient response inside the baseline's normal distribution does **not** trigger drift.

Quality metrics vs length metrics are defined explicitly in `QUALITY_METRICS` and `LENGTH_METRICS` in `profiles.py`.

### What this means in practice

| Scenario | Alerts? |
|----------|---------|
| Model gives shorter answer, verification depth unchanged | No |
| Model skips verification *and* depth drops *and* hedging shifts — all outliers vs baseline | Yes |
| Single metric wiggles slightly | No |

## Drift score

The `drift_score` (0–1) comes from `DiffEngine` comparing two fingerprints. It is a weighted summary of metric deltas — useful for ranking, not as a standalone alarm. The statistical outlier check gates actual alerts.

## Reports

```bash
cogscope report              # terminal summary, last 24 hours
cogscope report -o report.html   # HTML export
```

## Public tracker

Opt-in anonymous submissions feed the [Public Drift Log](../guides/public-drift-log.md). Your local prompts never leave your machine unless you run `cogscope submit` and confirm.

## Related

- [Fingerprinting](fingerprinting.md)
- [FAQ](../faq.md) — gaming and pseudo-science objections
