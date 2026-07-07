<p align="center">
  <img src="assets/logo-dark.svg" alt="Cogscope" width="140">
</p>

# Cogscope

**Long autonomous agent runs can look fine turn by turn while reasoning quietly collapses mid-session.**

**Cogscope is a local proxy that fingerprints how your coding agent reasons across an entire session, flags when verification behavior flattens out, and compares each turn to a baseline you pinned. No account. No cloud.**

## What it does

1. **Wrap** run any agent CLI through the local proxy with zero code changes (`cogscope wrap -- aider`).
2. **Capture** intercept LLM traffic through that proxy (or direct adapter calls).
3. **Fingerprint** extract numeric behavioral metrics from each response (depth, verification steps, hedging, and more).
4. **Track sessions** tag each turn with session id and turn number; detect verification variance collapse over long runs.
5. **Pin** save a baseline fingerprint for a task/model pair.
6. **Diff** compare new traffic against that baseline; alert only on corroborated statistical outliers.
7. **Check** validate a single prompt against a YAML policy in CI.

Nothing requires a cloud account. Data stays on your machine unless you explicitly run `cogscope submit`.

## Quick start

```bash
pipx install cogscope
cogscope quickstart
```

Or with pip inside a project environment: `pip install cogscope && cogscope quickstart`

Standalone binaries (no Python) are on [GitHub Releases](https://github.com/aadi-joshi/cogscope/releases).

`quickstart` runs in under a minute with **no API keys** and shows shallow reasoning blocked by a policy.

![Cogscope quickstart demo](assets/quickstart.gif)

## Recommended usage with an agent

```bash
cogscope init --yes
cogscope wrap -- aider          # or claude, python my_agent.py, etc.
```

In another terminal, optional live dashboard:

```bash
cogscope watch
```

See [Wrap your agent](guides/wrap-agent.md) for env vars, fallbacks, and limitations.

## How it differs from other tooling

| | Output-quality eval tools | Enterprise observability | Local agent firewalls | Cogscope |
|---|---------------------------|--------------------------|----------------------|----------|
| **Persona** | Benchmark / QA teams | ML platform, cloud dashboards | Developers running agents | Developers on long unattended agent runs |
| **Measures** | Final answers on fixed prompts | Latency, tokens, traces, costs | Spend, secrets, policy blocks | Reasoning shape + session trajectories |
| **Misses** | Mid-session collapse when each turn looks fine | Local session health for coding agents | Reasoning drift | Universal intelligence scoring |

See [Positioning and comparisons](concepts/positioning.md) for Guardian Runtime and observability platforms, and the [FAQ](faq.md) for skeptical questions answered honestly.

## Documentation map

| Section | What you'll learn |
|---------|-------------------|
| [Installation](getting-started/installation.md) | Install from PyPI or source |
| [Quickstart](getting-started/quickstart.md) | First run with zero configuration |
| [Wrap your agent](guides/wrap-agent.md) | Zero-code proxy instrumentation (recommended) |
| [Session trajectories](concepts/sessions.md) | Multi-turn collapse detection |
| [Positioning](concepts/positioning.md) | Guardian Runtime, observability tools, and Cogscope's niche |
| [Fingerprinting](concepts/fingerprinting.md) | What metrics mean (and what they don't) |
| [Writing a Policy](concepts/policies.md) | YAML policy schema and severity levels |
| [Drift Detection](concepts/drift.md) | When alerts fire, and when they don't |
| [CLI Reference](cli/reference.md) | Every command with verified examples |
| [Proxy & Privacy](guides/proxy-and-privacy.md) | What leaves your machine (nothing by default) |
| [Public Drift Log](guides/public-drift-log.md) | Community tracker and `cogscope submit` |
| [FAQ](faq.md) | Honest answers to skeptical questions |
| [Roadmap](roadmap.md) | What's in v0.1.0 and what's deferred |

## License

MIT. See [LICENSE](https://github.com/aadi-joshi/cogscope/blob/main/LICENSE) in the repository.
