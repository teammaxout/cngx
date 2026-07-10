# FAQ

## What does cngx actually do?

`cngx verify` runs the checks your AI coding agent claimed it ran, then compares the claim to reality. Example:

```bash
cngx verify --output-file agent_message.md -- pytest
```

It runs pytest, reads what the agent said in `agent_message.md`, and blocks (exit 1) when the agent claimed success but the tests fail, or when the agent's reported test counts do not match the real run. The verdict is bound to real command output, so it cannot be gamed by a "all tests pass" sentence. See the [Quickstart](getting-started/quickstart.md).

## Can an agent just write "all tests pass" to get through?

No. That is the whole point of `cngx verify`. It ignores the prose and runs the real command after `--` (or parses a real log with `--evidence-file`). If the agent says "3 passed, ready to merge" but pytest reports failures, the verdict is BLOCKED. The pass/fail comes from the process exit code, and parsed counts catch a claim that contradicts the real numbers.

This is different from the advanced `cngx check`, which only scores the *text* of agent output with heuristics and can be fooled by a fabricated claim (see below).

## Why is `cngx check` "advanced" and not the headline?

`cngx check` scores the text of agent output against a YAML policy using regex heuristics (verification phrases, reasoning depth, and so on). It does not run anything, so an agent that writes "I ran the tests, all 12 passed" without running anything can satisfy a text-only policy. It is useful as behavioral linting, not as proof of execution. For real proof, use `cngx verify`.

## Isn't the fingerprinting pseudo-science?

Partially, if you expect fingerprints to measure "true reasoning quality."

cngx does **not** claim to know what the model is thinking. It counts observable surface patterns: step structure, verification phrases, hedging language. Those are imperfect proxies. A model can perform genuine reasoning without trigger phrases, or paste "let me verify" without checking anything.

What cngx *does* claim:

1. **Consistency tracking**, when *your* model, on *your* tasks, suddenly shifts multiple behavioral metrics away from a baseline *you* pinned, that is worth investigating.
2. **Policy enforcement**, you can require minimum depth or verification counts for *your* deployment, knowing the check is heuristic.
3. **Honest limits**, we document regex-based metrics upfront (see [Fingerprinting](concepts/fingerprinting.md)).

It is closer to "behavioral linting" than "cognitive assessment." Useful for catching silent regressions after provider updates; not useful as a universal intelligence score.

## Can't a model just be prompted to fake verification steps?

Yes. If someone controls the prompt, they can add "let me verify" and bump `verification_steps` without real verification.

cngx is a **statistical signal against your own baseline**, not cheat-proof attestation:

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

## What statistical methods does cngx use?

| Situation | Methods |
|-----------|---------|
| Live `cngx watch` traffic | KSWIN + MDDM, multi-metric corroboration |
| `cngx diff` / population compare | Mann-Whitney U, Benjamini-Hochberg (1995), Cauchy Combination Test (Liu & Xie, 2020) |
| CI fixed benchmark regression (binary) | McNemar exact (holdout) |
| CI fixed benchmark regression (continuous) | Paired permutation test (holdout) |
| Optional `--semantic` | Local MiniLM embeddings + Jensen-Shannon distance |
| Optional `--otel` | OpenTelemetry GenAI spans + `cngx.fingerprint.*` attributes |

See [Drift detection](concepts/drift.md) for per-turn methods and [Session trajectories](concepts/sessions.md) for multi-turn collapse detection.

## How is this different from output benchmarks or observability tools?

| | Output-quality eval tools | Enterprise observability | Local agent firewalls | cngx |
|---|---------------------------|--------------------------|----------------------|----------|
| **Measures** | Final text, rubric scores, pass rates on fixed prompts | Latency, tokens, traces, spans, costs | Spend, secrets, policy blocks | Reasoning shape + session trajectories |
| **Baseline** | Global or hand-written test sets | Fleet dashboards | Static rules | *Your* pinned fingerprint |
| **Misses** | Mid-session collapse when each turn looks fine | Local long-run agent health | Reasoning drift | Universal intelligence scoring |

They are complementary. cngx catches the case where a long autonomous run still produces plausible output but verification quietly flattened across the session.

See [Positioning](concepts/positioning.md) for how this relates to Guardian Runtime (cost/security local proxy) and platforms like Langfuse or LangSmith.

## Does anything leave my machine?

Not unless you run `cngx submit` and confirm. See [Proxy and Privacy](guides/proxy-and-privacy.md).

## What models are supported?

Mock (no keys), OpenAI, Anthropic, and Google Gemini (optional extras). The proxy forwards OpenAI and Anthropic API shapes today.

Install extras with pipx: `pipx inject cngx "google-genai>=1.0.0"`. Or with pip: `pip install "cngx[gemini]"`.

## Where is the code?

| Component | Path |
|-----------|------|
| Fingerprinting | `cngx/fingerprint/` |
| Policies | `cngx/contracts/` |
| Drift | `cngx/drift/`, `cngx/calibration/` |
| Proxy | `cngx/proxy/` |
| CLI | `cngx/cli/` |

## What's planned next?

See [Roadmap](roadmap.md).
