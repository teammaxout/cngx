# Cogscope

**Output metrics can stay flat while reasoning gets shallower.**

**Cogscope fingerprints how a model reasons, compares it to a pinned baseline, and flags drift on your machine. No account. No cloud.**

[![CI](https://github.com/aadi-joshi/cogscope/actions/workflows/ci.yml/badge.svg)](https://github.com/aadi-joshi/cogscope/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

Providers ship model updates often. Latency and error rates look fine. The final answer may still read well. What changes is the reasoning underneath: fewer verification steps, shallower chains of thought, more confident guesses.

Most evals score the output text. They miss the case where the answer looks right today but wrong tomorrow because the model stopped checking its work. Cogscope tracks **how** the model reasoned (depth, verification, hedging, corrections) and compares that shape to behavior you have already pinned as normal.

### How this compares

| | Output-quality eval tools | Telemetry / observability tools | Cogscope |
|---|---------------------------|----------------------------------|----------|
| **What they measure** | Final answers, rubric scores, benchmark pass rates on fixed prompts | Latency, tokens, traces, spans, costs, error rates in production | Reasoning-shape metrics: depth, verification steps, hedging, corrections |
| **Baseline** | Global benchmarks or hand-written test sets | Fleet aggregates and dashboards | *Your* pinned fingerprint for *your* task and model |
| **What they miss** | Shallow reasoning when the answer still reads well | Whether reasoning behavior drifted from what you accepted before | Semantic understanding of "true" reasoning; cheat-proof attestation |
| **Typical use** | Pre-release regression suites | Production monitoring and debugging | Local proxy, CI policy checks, baseline-relative drift alerts |

These approaches are complementary. Cogscope targets the gap where output still passes but verification quietly disappeared.

---

## Demo

Terminal recording of `cogscope quickstart` (mock adapter, no API keys, generated with [VHS](https://github.com/charmbracelet/vhs)):

![Cogscope quickstart: shallow reasoning ships without Cogscope, policy check BLOCKED with Cogscope](docs/assets/quickstart.gif)

```bash
pip install -e .
cogscope quickstart
```

Regenerate after UI changes: `vhs scripts/demo/quickstart.tape` (see `scripts/demo/README.md`).

---

## Public drift tracker

The [Cogscope Drift Tracker](https://aadi-joshi.github.io/cogscope/) is a static site of opt-in, anonymous fingerprint trends (depth, verification, hedging, drift vs each submitter's baseline). No prompts or outputs are published.

![Cogscope drift tracker: model tabs, charts, and hover interaction](docs/assets/tracker-demo.gif)

[Full demo (MP4)](docs/assets/tracker-demo.mp4) · [Static screenshot](docs/assets/tracker-demo.png) · [Contribute data](docs/guides/public-drift-log.md)

Regenerate the recording: `python scripts/demo/record_tracker.py` (see `scripts/demo/README.md`).

---

## Install and try it

```bash
git clone https://github.com/aadi-joshi/cogscope.git
cd cogscope
pip install -e .
cogscope quickstart
```

`quickstart` runs a mock scenario: a pipeline that accepts shallow reasoning, then shows Cogscope blocking the same behavior against a policy. No configuration or keys. Under 30 seconds.

Initialize a project directory (creates `.cogscope/` and a local DuckDB store):

```bash
cogscope init --yes
```

---

## How it works

Point your app at the local proxy instead of the provider. Cogscope forwards traffic unchanged, fingerprints each completed response on the side (without delaying the stream), and compares new fingerprints to a baseline you pin.

```
  Your app          Cogscope proxy          Provider API
      │                    │                      │
      │  chat request      │  forward (same body) │
      ├───────────────────►├─────────────────────►
      │                    │                      │
      │  streamed response │◄─────────────────────┤
      ◄────────────────────┤                      │
      │                    │                      │
      │                    ├── capture trace       │
      │                    ├── fingerprint metrics │
      │                    ├── diff vs baseline   │
      │                    └── alert if outlier   │
```

| Step | What happens |
|------|----------------|
| **Capture** | Every proxied call becomes a `ReasoningTrace` (prompt, output, reasoning text, tokens). |
| **Fingerprint** | Heuristic metrics: reasoning depth, verification steps, hedging ratio, corrections, and more. |
| **Pin** | `cogscope pin --label baseline` saves "normal" for a task/model pair. |
| **Diff** | Live traffic is compared to that baseline. Alerts require corroborated statistical outliers, not a single short answer. |

**Detection methods (by path):**

- **Live proxy (`watch`)**: ADWIN and Page-Hinkley streaming tests per metric (via [frouros](https://github.com/IFCA/frouros)). At least two metric streams must flag drift, including a quality metric. Length-only shifts do not alert alone.
- **Batch diff (`diff`, `check` populations)**: Mann-Whitney U per metric, Benjamini-Hochberg FDR correction, then Fisher's method for an omnibus call.
- **CI regression (`regression`)**: McNemar's test on paired correct/incorrect outcomes when you have a fixed benchmark suite and oracle.
- **Optional (`watch --semantic`)**: local sentence-transformer embeddings and Jensen-Shannon distance (`pip install cogscope[semantic]`).

### Day-to-day commands

```bash
# Local proxy + live terminal dashboard (default http://127.0.0.1:8642)
cogscope watch

# Pin the latest capture as your baseline
cogscope pin --label baseline

# One-shot diff of recent traffic vs baseline
cogscope diff --baseline baseline

# Policy check for CI (exit 0 pass, 1 blocked, 2 failed)
cogscope check -c examples/contracts/basic_reasoning.yaml "Your prompt here"

# Drift summary over the last 24 hours
cogscope report
```

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` in your environment before `watch`. Keys stay in memory for forwarding only and are never written to the local database.

---

## What this is NOT

- **Not a universal intelligence score.** Metrics are relative to *your* pinned baseline for *your* task, not a leaderboard across models.
- **Not proof of provider wrongdoing.** Cogscope shows statistical deviation from behavior you recorded. It does not adjudicate intent or fault.
- **Not cheat-proof.** Someone optimizing specifically against these heuristics can game them. Treat alerts as signals to investigate, not verdicts.
- **Not alarmed by efficiency alone.** A model that becomes more concise **without** losing verification depth or other quality signals should **not** trigger a drift alert. Alerting requires corroborated, multi-metric outliers relative to your baseline distribution (see `cogscope/drift/detector.py`).

---

## Limitations (read this)

Fingerprint metrics are **heuristic and regex-based**, not semantic understanding. They count patterns like "let me verify", step labels, and uncertainty markers. Those are useful proxies, not ground truth. A model can appear deep while reasoning poorly, or concise while still being rigorous. Calibration improves with more baseline history, but this will never replace human review for high-stakes decisions.

---

## Local-first, no cloud

Cogscope runs entirely on your machine. No account, no telemetry, no bill. Traces and fingerprints live in a local DuckDB file under `.cogscope/`. The proxy binds to `127.0.0.1` by default. The only data that leaves your machine is what you explicitly choose to send via `cogscope submit` after a preview-and-confirm step.

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, style, and how to add metrics or adapters.

---

## License

MIT. See [LICENSE](LICENSE).
