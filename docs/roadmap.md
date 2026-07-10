# cngx Roadmap

cngx **v0.2.0** is a deliberately narrow open-source tool. The flagship is `cngx verify`:
run the checks an AI agent claimed it ran and block the merge on a false claim. Everything
else (heuristic policy lint, drift engine, community tracker) is advanced. Not a full AI platform.

## What ships today (v0.2.0)

| Capability | Status |
|------------|--------|
| `cngx verify` (run the claimed command, block false claims) | Shipped |
| `--output-file` / `--stdin` / `--claim` claim sources | Shipped |
| Command execution after `--`, or `--evidence-file` for existing logs | Shipped |
| Result parsers: pytest, unittest, jest/vitest, go test, cargo test, generic | Shipped |
| `--require-claim`, `--timeout`, `--json` | Shipped |
| Zero-key `cngx quickstart` (real tests, false claim blocked) | Shipped |
| GitHub Action with `command` input | Shipped |
| Advanced: heuristic `cngx check` policy lint | Shipped |
| Advanced: local ASGI proxy (`cngx watch` / `cngx wrap`) | Shipped |
| Advanced: behavioral fingerprinting (regex/heuristic metrics) | Shipped |
| Advanced: baseline pinning and multi-metric drift alerts | Shipped |
| Advanced: paired regression suites (`cngx regression`) | Shipped |
| Advanced: opt-in public drift tracker (`cngx submit`) | Shipped |

**Design principles:**

- Verify is bound to real command output; it cannot be gamed by prose
- Local-first, no account, no telemetry by default
- Text policies (`cngx check`) are heuristics; use `cngx verify` for real proof
- Advanced drift alerts are relative to *your* pinned baseline, not universal thresholds
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
