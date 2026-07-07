# FAQ

## Isn't this pseudo-science?

Partially — if you expect fingerprints to measure "true reasoning quality."

Cogscope does **not** claim to know what the model is thinking. It counts observable surface patterns: step structure, verification phrases, hedging language. Those are imperfect proxies. A model can perform genuine reasoning without trigger phrases, or paste "let me verify" without checking anything.

What Cogscope *does* claim:

1. **Consistency tracking** — when *your* model, on *your* tasks, suddenly shifts multiple behavioral metrics away from a baseline *you* pinned, that is worth investigating.
2. **Policy enforcement** — you can require minimum depth or verification counts for *your* deployment, knowing the check is heuristic.
3. **Honest limits** — we document regex-based metrics upfront (see [Fingerprinting](concepts/fingerprinting.md)).

It is closer to "behavioral linting" than "cognitive assessment." Useful for catching silent regressions after provider updates; not useful as a universal intelligence score.

## Can't a model just be prompted to fake verification steps?

Yes. If someone controls the prompt, they can add "let me verify" and bump `verification_steps` without real verification.

Cogscope is a **statistical signal against your own baseline**, not cheat-proof attestation:

- **Drift alerts** require multiple quality metrics to move together relative to *your* history — gaming one phrase is insufficient.
- **Policies** can combine verification counts with depth, step count, and pattern rules — raising the cost of trivial gaming.
- **It does not** detect sophisticated adversarial mimicry optimized specifically against these regexes.

Treat alerts as "investigate this response," not "the model is broken." For high-stakes decisions, human review still matters.

## Why doesn't a shorter answer trigger drift?

By design. Efficiency is not degradation.

Alerting logic (`cogscope/calibration/profiles.py`, `cogscope/drift/detector.py`):

- Compare against the pinned baseline's **distribution**, not fixed universal numbers
- Require **≥2 outlier metrics**, including at least one quality metric
- **Length-only changes never alert alone**

A model that becomes more concise while keeping verification depth and other quality signals in range should not fire a false alarm. This is tested in `tests/unit/test_drift_alerting.py`.

## How is this different from output benchmarks?

| Output benchmarks | Cogscope |
|-------------------|----------|
| Score final text | Score reasoning shape |
| Often one-off eval sets | Continuous capture on your traffic |
| Compare models globally | Compare against *your* baseline |
| Pass/fail on answers | Detect behavioral shift |

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
