# Roadmap

The canonical roadmap document is maintained at the repository root:

**[ROADMAP.md](https://github.com/aadi-joshi/cogscope/blob/main/ROADMAP.md)**

## v0.1.0 scope (current)

Cogscope v0.1.0 is deliberately narrow:

- Local proxy with side-channel fingerprinting
- DuckDB storage under `.cogscope/`
- YAML policies and `cogscope check` for CI
- Baseline pinning and multi-metric drift alerts
- Live TUI during `cogscope watch`
- Opt-in public tracker via `cogscope submit`

This is the full OSS tool — not a stripped-down demo of a larger platform.

## Deferred, not abandoned

Phase 2 modules (correctness validators, consensus, benchmarks, etc.) exist in `_archive_pre_oss/` and may return based on community demand. See the root ROADMAP for the full list.

## Archived SaaS

The previous cloud dashboard and enterprise platform also live in `_archive_pre_oss/`. They could inform a future hosted offering but are **not** part of v0.1.0 and **not** required for the local tool to work.
