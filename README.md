# cngx

[![CI](https://github.com/aadi-joshi/cngx/actions/workflows/ci.yml/badge.svg)](https://github.com/aadi-joshi/cngx/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/cngx/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

cngx checks whether a coding agent actually ran the verification your policy requires before you trust its output.

```bash
pipx install cngx
cngx quickstart          # mock demo, no API keys, under 30s
```

```bash
cngx check -c examples/contracts/basic_reasoning.yaml "Fix the bug and run the test suite"
```

Gate existing agent output with no provider calls:

```bash
cngx check -c examples/contracts/coding_agent_fix.yaml \
  -p "Fix the pagination bug and run tests" \
  --output-file agent_output.txt
```

Python 3.10+. Requires [pipx](https://pipx.pypa.io/) or `pip install cngx`. See [installation](docs/getting-started/installation.md).

## What it does

**Message one (no baseline):** `cngx check` fingerprints a single response and enforces a behavior policy. Did the model verify its work (tests, repro steps, explicit checks) or only sound confident?

**Long sessions:** `cngx wrap` and `cngx watch` proxy your agent, fingerprint every call, and compare live traffic to a baseline you pin. Alerts use corroborated statistical tests, not length alone.

```
  agent ──► cngx proxy ──► provider API
              │
              ├── fingerprint each response
              ├── cngx check / policy gate (optional)
              └── diff vs pinned baseline (session drift)
```

## Measured (synthetic benchmarks, alpha=0.05)

| Scenario | Method | False positive rate |
|----------|--------|---------------------|
| Correlated stationary, no drift (250 trials) | Legacy Fisher omnibus | 0.024 (6/250) |
| Correlated stationary, no drift (250 trials) | CCT batch (current) | 0.024 (6/250) |
| Independent stationary, no drift (250 trials) | Legacy (>=2 metrics) | 0.016 (4/250) |
| Independent stationary, no drift (250 trials) | CCT batch (current) | 0.032 (8/250) |
| Streaming stable series (150 steps) | KSWIN / MDDM | 0.000 (0/150) |
| Streaming stable series (150 steps) | Legacy ADWIN / Page-Hinkley | 0.000 (0/150) |

| Detection | Result |
|-----------|--------|
| Streaming shift (injected at step 80) | First KSWIN/MDDM alert at step 87 |
| Session verification collapse (synthetic) | Collapse from turn 13, warning at turn 22 (9-turn delay) |
| McNemar suite shift (binary) | p ≈ 0.000002 |
| Paired permutation (continuous) | p = 0.0002 |

Synthetic draws only. Pin your own baseline on real traffic before treating alerts as production signals. Details: [drift engine](docs/concepts/drift.md), [sessions](docs/concepts/sessions.md).

## Commands

| Command | Use |
|---------|-----|
| `cngx quickstart` | Zero-key demo: unverified agent patch blocked |
| `cngx check -c policy.yaml "…"` | One-shot policy check (CI-friendly exit codes) |
| `cngx check -c policy.yaml --output-file out.txt` | Gate existing agent output offline |
| `cngx wrap -- aider` | Route an agent through the local proxy |
| `cngx watch` | Live dashboard on proxied traffic |
| `cngx pin --label baseline` | Save normal behavior for a task |
| `cngx diff --baseline baseline` | Compare recent captures to that baseline |
| `cngx submit --baseline baseline` | Opt-in metrics to the [community tracker](https://aadi-joshi.github.io/cngx/) |

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` for live providers. Keys stay in memory for forwarding; they are not written to the local database.

## Local-first

Runs on your machine. Traces and fingerprints live in `.cngx/` (DuckDB). Proxy binds to `127.0.0.1` by default. Nothing leaves the host unless you run `cngx submit` after an explicit preview and confirm (numeric metrics only; no personal identity collected or stored).

## Docs

- [Quickstart](docs/getting-started/quickstart.md)
- [Proxy and privacy](docs/guides/proxy-and-privacy.md)
- [CLI reference](docs/cli/reference.md)
- [Contributing](CONTRIBUTING.md)

Created by [Kavya Bhand](https://github.com/kavyabhand) and [Aadi Joshi](https://github.com/aadi-joshi).

MIT. See [LICENSE](LICENSE).
