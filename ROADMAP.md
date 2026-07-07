# Cogscope Roadmap

Cogscope v0.1.0 is a **deliberately narrow** open-source tool. The scope is intentional: local fingerprinting, baseline-relative drift, and policy checks — not a full AI platform.

This document explains what ships today, what was archived for Phase 2, and what that means for the future.

---

## v0.1.0 — What you get today

| Capability | Status |
|------------|--------|
| Local ASGI proxy (`cogscope watch`) | Shipped |
| Behavioral fingerprinting (regex/heuristic metrics) | Shipped |
| DuckDB local storage (`.cogscope/`) | Shipped |
| Baseline pinning (`cogscope pin`) | Shipped |
| Multi-metric statistical drift alerts | Shipped |
| YAML policies + `cogscope check` (CI exit codes) | Shipped |
| Live terminal dashboard (Rich TUI) | Shipped |
| Opt-in public drift tracker (`cogscope submit`) | Shipped |
| Zero-key `cogscope quickstart` | Shipped |

**Design principles baked in:**

- Local-first — no account, no telemetry
- Alerts relative to *your* pinned baseline, not universal thresholds
- Shorter answers alone do not trigger drift
- Privacy — submit shares numeric metrics only, with preview-and-confirm

---

## Phase 2 candidates — deferred, not in this repository

The following capabilities were explored during early development and are **intentionally deferred** pending real community demand. They are **not** part of v0.1.0 and **not** included in this repository.

| Capability | What it would add |
|------------|-------------------|
| **Correctness validators** | Math/code/logic answer validation beyond behavioral metrics |
| **Cross-model consensus** | Agreement checks across multiple models |
| **Benchmarking harness** | Structured benchmark runs and comparisons |
| **Robustness / perturbation** | Prompt perturbation and stability testing |
| **Explainability engine** | Natural-language violation explanations |
| **Remediation engine** | Automated fix suggestions for failed checks |
| **Audit logging** | Tamper-evident trails for policy decisions |
| **Cross-model validator** | Cross-model agreement checks |

Associated tests for these areas are likewise out of scope for v0.1.0.

### When might Phase 2 return?

When there is clear, sustained demand from OSS users — e.g. issues asking for math correctness validation, cross-model consensus, or benchmark harnesses — with contributors willing to maintain them outside the core local tool.

The core tool must stay simple. Phase 2 features will not be merged back without a strong case that they serve the local-first use case.

---

## Hosted platform — out of scope for v0.1.0

A previous product direction included a multi-service hosted stack (dashboard, team features, cloud SDK). That work is **not** part of this repository or v0.1.0. The local OSS tool is complete without it. A future hosted offering could revisit shared baselines or team dashboards based on demand, but nothing here commits to that.

---

## Near-term OSS priorities (informal)

Not committed dates — direction based on the oss-launch sequence:

1. **Docs and launch polish** — mkdocs, README, demo GIF
2. **Tracker community growth** — opt-in submissions, cited model-update annotations
3. **Adapter coverage** — broader provider API shapes through the proxy
4. **Policy examples** — domain-specific templates contributed by users

---

## What we will not do in core v0.x without strong justification

- Require a cloud account to use the tool
- Phone home telemetry by default
- Present fingerprints as universal intelligence scores
- Re-introduce hosted billing, RBAC, or multi-tenant SaaS into the default install

---

## How to influence the roadmap

Open a [feature request](https://github.com/aadi-joshi/cogscope/issues/new?template=feature_request.md) with your use case. Phase 2 restorations will be driven by evidence of demand, not by restoring everything from archive.
