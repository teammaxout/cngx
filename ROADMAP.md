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

## Phase 2 candidates — deferred, not deleted

The following modules were **archived intact** under `_archive_pre_oss/rvc/` during the oss-launch pivot. They exist, work (within the old SaaS context), and are **intentionally deferred** pending real community demand — not abandoned or vaporware.

| Module | Location | What it did |
|--------|----------|-------------|
| **Correctness validators** | `rvc/correctness/` | Math/code/logic answer validation beyond behavioral metrics |
| **Cross-model consensus** | `rvc/consensus/` | Agreement checks across multiple models |
| **Benchmarking harness** | `rvc/benchmarks/` | Structured benchmark runs and comparisons |
| **Robustness / perturbation** | `rvc/robustness/` | Prompt perturbation and stability testing |
| **Explainability engine** | `rvc/explain/` | Natural-language violation explanations |
| **Remediation engine** | `rvc/remediation/` | Automated fix suggestions for failed checks |
| **Governance / audit logging** | `rvc/governance/` | Tamper-evident audit trails and compliance logging |
| **Cross-model validator** | `rvc/crossmodel/` | `CrossModelValidator` (~365 lines) |

Associated tests were archived alongside these modules (see `_archive_pre_oss/README.md`).

### When might Phase 2 return?

When there is clear, sustained demand from OSS users — e.g. issues asking for math correctness validation, cross-model consensus, or benchmark harnesses — with contributors willing to maintain them outside the core local tool.

The core tool must stay simple. Phase 2 features will not be merged back without a strong case that they serve the local-first use case, not just the old enterprise product.

---

## Archived SaaS platform — reference only

The previous product included a full hosted stack. It remains in `_archive_pre_oss/` for reference:

| Path | Contents |
|------|----------|
| `rvc-demo/` | Self-contained SaaS demo (FastAPI + React) |
| `rvc-prod/` | Investor/production SaaS snapshot |
| `rvc/platform/` | Enterprise platform (billing, workers, 55+ routes) |
| `rvc/cloud/` | Lightweight multi-tenant cloud + Jinja UI |
| `rvc/sdk/` | Cloud SDK (22+ endpoints) |
| `website/` | Old marketing site |
| `docker-compose.yml` | Multi-service deployment |

**This could inform a future hosted offering** — dashboards, team baselines, shared tracker — but v0.1.0 does **not** commit to one. The OSS tool is complete without it.

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
- Re-introduce enterprise billing, RBAC, or multi-tenant SaaS into the default install

---

## How to influence the roadmap

Open a [feature request](https://github.com/aadi-joshi/cogscope/issues/new?template=feature_request.md) with your use case. Phase 2 restorations will be driven by evidence of demand, not by restoring everything from archive.
