# cngx Roadmap

cngx **v0.1.7** is a deliberately narrow open-source tool: local fingerprinting,
offline agent gating, baseline-relative drift, and policy checks. Not a full AI platform.

## What ships today (v0.1.7)

| Capability | Status |
|------------|--------|
| Offline `cngx check --output-file` | Shipped |
| `--evidence-file` cross-check for pytest/CI logs | Shipped |
| Coding-agent verification policies | Shipped |
| Local ASGI proxy (`cngx watch` / `cngx wrap`) | Shipped |
| Behavioral fingerprinting (regex/heuristic metrics) | Shipped |
| DuckDB local storage (`.cngx/`) | Shipped |
| Baseline pinning (`cngx pin`) | Shipped |
| Multi-metric statistical drift alerts | Shipped |
| Paired regression suites (`cngx regression`) | Shipped |
| Live terminal dashboard (Rich TUI) | Shipped |
| Opt-in public drift tracker (`cngx submit`) | Shipped |
| Zero-key `cngx quickstart` | Shipped |
| GitHub Action (offline + live) | Shipped |

**Design principles:**

- Local-first, no account, no telemetry by default
- Alerts relative to *your* pinned baseline, not universal thresholds
- Shorter answers alone do not trigger drift
- Text policies are heuristics; use `--evidence-file` and CI exit codes for stronger gates
- Privacy: submit shares numeric metrics only, with preview-and-confirm

## Near-term priorities

1. Artifact-aware CI examples (pytest log + agent output in one Action)
2. Broader provider shapes through the proxy (Gemini wrap honesty or real route)
3. Docs site deploy (MkDocs) separate from the tracker homepage
4. More policy templates from real agent workflows

## Deferred (not in this repository)

| Capability | Notes |
|------------|-------|
| Correctness validators (math/code answer checking) | Explored earlier; not in OSS tree |
| Cross-model consensus | Deferred |
| Robustness / perturbation harness | Deferred |
| Explainability / remediation engines | Deferred |
| Hosted multi-tenant SaaS | Out of scope for core |

## What we will not do in core v0.x without strong justification

- Require a cloud account to use the tool
- Phone-home telemetry by default
- Present fingerprints as universal intelligence scores
- Re-introduce hosted billing, RBAC, or multi-tenant SaaS into the default install
