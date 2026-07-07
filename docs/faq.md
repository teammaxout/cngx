# FAQ

## Isn't this pseudo-science?

Partially, if you expect fingerprints to measure "true reasoning quality."

Cogscope does **not** claim to know what the model is thinking. It counts observable surface patterns: step structure, verification phrases, hedging language. Those are imperfect proxies. A model can perform genuine reasoning without trigger phrases, or paste "let me verify" without checking anything.

What Cogscope *does* claim:

1. **Consistency tracking**, when *your* model, on *your* tasks, suddenly shifts multiple behavioral metrics away from a baseline *you* pinned, that is worth investigating.
2. **Policy enforcement**, you can require minimum depth or verification counts for *your* deployment, knowing the check is heuristic.
3. **Honest limits**, we document regex-based metrics upfront (see [Fingerprinting](concepts/fingerprinting.md)).

It is closer to "behavioral linting" than "cognitive assessment." Useful for catching silent regressions after provider updates; not useful as a universal intelligence score.

## Can't a model just be prompted to fake verification steps?

Yes. If someone controls the prompt, they can add "let me verify" and bump `verification_steps` without real verification.

Cogscope is a **statistical signal against your own baseline**, not cheat-proof attestation:

- **Drift alerts** require multiple quality metrics to move together relative to *your* history, gaming one phrase is insufficient.
- **Policies** can combine verification counts with depth, step count, and pattern rules, raising the cost of trivial gaming.
- **It does not** detect sophisticated adversarial mimicry optimized specifically against these regexes.

Treat alerts as "investigate this response," not "the model is broken." For high-stakes decisions, human review still matters.

## Why doesn't a shorter answer trigger drift?

By design. Efficiency is not structural regression.

**Live proxy (streaming):** KSWIN and MDDM monitor each metric stream relative to your pinned baseline history. Structural drift alerts require at least two streams to flag, excluding length-only shifts.

**Batch diff/check:** Mann-Whitney p-values are combined with Benjamini-Hochberg FDR correction and the Cauchy Combination Test (CCT). Length-only BH rejections are explicitly guarded.

A model that becomes more concise while keeping verification depth and other fingerprint signals in range should not fire a false alarm. This is tested in `tests/unit/test_drift_alerting.py`.

## What is structural drift vs semantic drift?

| | Structural drift | Semantic drift |
|---|------------------|----------------|
| **Signal** | Heuristic fingerprint metrics (regex counts) | Optional local embeddings (`--semantic`) |
| **Means** | Reasoning *shape* changed vs your baseline | *Content* distribution shifted |
| **Implies** | Something changed, investigate | Topical or semantic shift detected |
| **Does NOT prove** | The model got worse | The model got worse |

Provider system-prompt tweaks toward conciseness often trigger structural drift without any capability loss. Treat alerts as "go look," not "regression confirmed."

## What statistical methods does Cogscope use?

| Situation | Methods |
|-----------|---------|
| Live `cogscope watch` traffic | KSWIN + MDDM, multi-metric corroboration |
| `cogscope diff` / population compare | Mann-Whitney U, Benjamini-Hochberg (1995), Cauchy Combination Test (Liu & Xie, 2020) |
| CI fixed benchmark regression (binary) | McNemar exact (holdout) |
| CI fixed benchmark regression (continuous) | Paired permutation test (holdout) |
| Optional `--semantic` | Local MiniLM embeddings + Jensen-Shannon distance |
| Optional `--otel` | OpenTelemetry GenAI spans + `cogscope.fingerprint.*` attributes |

See [Drift detection](concepts/drift.md) for per-turn methods and [Session trajectories](concepts/sessions.md) for multi-turn collapse detection.

## How is this different from output benchmarks?

| | Output-quality eval tools | Telemetry / observability tools | Cogscope |
|---|---------------------------|----------------------------------|----------|
| **Measures** | Final text, rubric scores, pass rates on fixed prompts | Latency, tokens, traces, spans, costs | Reasoning shape: depth, verification, hedging |
| **Baseline** | Global or hand-written test sets | Fleet dashboards | *Your* pinned fingerprint |
| **Misses** | Silent shallow reasoning when answers still look fine | Whether reasoning drifted from what you accepted | Universal intelligence scoring |

They are complementary. Cogscope catches the case where answers still look fine but reasoning got shallower.

## Does anything leave my machine?

Not unless you run `cogscope submit` and confirm. See [Proxy and Privacy](guides/proxy-and-privacy.md).

## What models are supported?

Mock (no keys), OpenAI, Anthropic, and Google Gemini (optional extras). The proxy forwards OpenAI and Anthropic API shapes today.

## Where is the code?

| Component | Path |
|-----------|------|
| Fingerprinting | `cogscope/fingerprint/` |
| Policies | `cogscope/contracts/` |
| Drift | `cogscope/drift/`, `cogscope/calibration/` |
| Proxy | `cogscope/proxy/` |
| CLI | `cogscope/cli/` |

## What's planned next?

See [Roadmap](roadmap.md).
