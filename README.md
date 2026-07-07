# Cogscope

**Long autonomous agent runs can look fine turn by turn while reasoning quietly collapses mid-session.**

**Cogscope is a local proxy that fingerprints how your coding agent reasons across an entire session, flags when verification behavior flattens out, and compares each turn to a baseline you pinned. No account. No cloud.**

[![CI](https://github.com/aadi-joshi/cogscope/actions/workflows/ci.yml/badge.svg)](https://github.com/aadi-joshi/cogscope/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## The problem

You leave Aider, Cline, Claude Code, or another agent on a long unattended run. Every individual response still reads fine. Latency looks normal. The diff gets longer. But somewhere around turn 80 the agent stops actually checking its own work: verification steps flatten to a fixed, shallow pattern while output stays verbose.

Single-response evals and production dashboards miss this. They score outputs or fleet aggregates, not whether *your* agent's reasoning trajectory stayed healthy across hundreds of turns. Cogscope sits on your machine as a local proxy, fingerprints each turn (depth, verification steps, hedging, corrections), tracks session-level trajectories, and alerts when behavior drifts from what you pinned, including session stability warnings when verification variance collapses.

Per-turn structural drift detection is a supporting capability. The headline scenario is **silent mid-session reasoning collapse on long autonomous runs**.

### How this compares

| | Output-quality eval tools | Enterprise observability (Langfuse, LangSmith, Arize, …) | Local agent firewalls (cost/security) | Cogscope |
|---|---------------------------|----------------------------------------------------------|---------------------------------------|----------|
| **Persona** | Benchmark authors, QA | ML platform teams, cloud dashboards | Developers running autonomous agents | Developers running long unattended agent sessions |
| **What they measure** | Final answers on fixed prompts | Latency, tokens, traces, costs, post-hoc analysis | Spend limits, secrets, policy blocks | Reasoning-shape metrics and session trajectories on *your* traffic |
| **Baseline** | Global benchmarks | Fleet aggregates | Static rules | *Your* pinned fingerprint |
| **Typical gap** | Shallow reasoning when answers still read well | Not aimed at local agent session health | Does not watch reasoning drift | Semantic ground truth; cheat-proof attestation |

These approaches are complementary. Cogscope targets the gap where each turn looks fine but verification quietly stopped varying across the session.

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

**Recommended** (isolated CLI on your PATH, no virtualenv to manage):

```bash
pipx install cogscope
cogscope quickstart
```

Requires [pipx](https://pipx.pypa.io/). Python 3.10+ must be installed on your system, but you do not need to create or activate a virtual environment.

**Alternatives:**

```bash
# Inside a project virtualenv
pip install cogscope

# No Python install: download a standalone binary from GitHub Releases
# https://github.com/aadi-joshi/cogscope/releases
```

`quickstart` runs a mock scenario with no API keys or configuration. Under 30 seconds.

Initialize a project directory (creates `.cogscope/` and a local DuckDB store):

```bash
cogscope init --yes
```

No Docker required for normal use. Docker is optional only if you want to containerize the proxy on a server (see [Installation](docs/getting-started/installation.md)).

---

## Recommended: wrap your agent (zero code changes)

Point traffic through Cogscope without editing the agent's config:

```bash
# Starts the proxy if needed, injects SDK base URLs, runs your command
cogscope wrap -- aider
cogscope wrap -- claude
cogscope wrap -- python my_agent.py
```

`wrap` sets `OPENAI_BASE_URL`, `OPENAI_API_BASE`, and `ANTHROPIC_BASE_URL` in the child process so OpenAI- and Anthropic-compatible SDKs route through `http://127.0.0.1:8642` automatically. Set your provider API keys in the environment as usual.

For a live dashboard while the agent runs, use a second terminal:

```bash
cogscope watch
```

Or combine session tracking:

```bash
cogscope wrap --session-id my-long-run -- aider
```

See [Proxy and Privacy](docs/guides/proxy-and-privacy.md) for manual base-URL setup (fallback for tools that ignore env overrides) and [Session trajectories](docs/concepts/sessions.md) for collapse detection.

---

## How it works

Cogscope forwards provider traffic unchanged, fingerprints each completed response on the side (without delaying the stream), and compares new fingerprints to a baseline you pin.

```
  Your agent         Cogscope proxy          Provider API
      │                    │                      │
      │  chat request      │  forward (same body) │
      ├───────────────────►├─────────────────────►
      │                    │                      │
      │  streamed response │◄─────────────────────┤
      ◄────────────────────┤                      │
      │                    │                      │
      │                    ├── capture trace       │
      │                    ├── fingerprint metrics │
      │                    ├── session trajectory  │
      │                    ├── diff vs baseline   │
      │                    └── alert if outlier   │
```

| Step | What happens |
|------|----------------|
| **Capture** | Every proxied call becomes a `ReasoningTrace` (prompt, output, reasoning text, tokens). |
| **Fingerprint** | Heuristic metrics: reasoning depth, verification steps, hedging ratio, corrections, and more. |
| **Session track** | Each turn is tagged with `session_id` and turn number; collapse detection watches verification variance over time. |
| **Pin** | `cogscope pin --label baseline` saves "normal" for a task/model pair. |
| **Diff** | Live traffic is compared to that baseline. Alerts require corroborated statistical outliers, not a single short answer. |

**Detection methods (by path):**

- **Live proxy (`watch` / `wrap`)**: KSWIN and MDDM streaming tests per metric (via [frouros](https://github.com/IFCA/frouros)). At least two metric streams must flag structural drift. Length-only shifts do not alert alone.
- **Session trajectories**: rolling verification variance collapse rule after 20+ turns (distinct **session stability warning**).
- **Batch diff (`diff`, `check` populations)**: Mann-Whitney U per metric, Benjamini-Hochberg FDR correction, then the Cauchy Combination Test (CCT) for an omnibus call that handles correlated metrics.
- **CI regression (`regression`)**: McNemar's exact test (binary) or paired permutation test (continuous) on fixed benchmark suites with an oracle.
- **Optional (`watch --semantic`)**: local sentence-transformer embeddings and Jensen-Shannon distance for **semantic drift** (`pip install cogscope[semantic]`).
- **Optional (`watch --otel`)**: OTel GenAI spans with fingerprint attributes to OTLP (`pip install cogscope[otel]`).

**Structural vs semantic drift:** Heuristic fingerprint shifts are *structural drift* (something changed in reasoning shape, often provider tuning). Embedding shifts are *semantic drift*. Neither alone proves the model got worse.

### Day-to-day commands

```bash
# Zero-code instrumentation for an existing agent CLI
cogscope wrap -- aider

# Local proxy + live terminal dashboard (default http://127.0.0.1:8642)
cogscope watch

# Pin the latest capture as your baseline
cogscope pin --label baseline

# Session trajectory report
cogscope report --session my-long-run

# One-shot diff of recent traffic vs baseline
cogscope diff --baseline baseline

# Policy check for CI (exit 0 pass, 1 blocked, 2 failed)
cogscope check -c examples/contracts/basic_reasoning.yaml "Your prompt here"
```

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` in your environment before `wrap` or `watch`. Keys stay in memory for forwarding only and are never written to the local database.

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
git clone https://github.com/aadi-joshi/cogscope.git
cd cogscope
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, style, and how to add metrics or adapters.

---

## License

MIT. See [LICENSE](LICENSE).
