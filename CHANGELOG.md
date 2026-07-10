# Changelog

All notable changes to cngx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.5] - 2026-07-10

### Fixed
- Standalone PyInstaller binaries now bundle pydantic and related imports (Windows builds were crashing on startup).
- Release binary smoke test runs an offline `cngx check` and expects a policy fail, not an import crash.
- GitHub Action generator emits a real offline `cngx check` workflow (no fake `benchmark` / `consensus` steps).
- Docs no longer claim zero added proxy latency; fingerprinting is background after the stream.
- Broken tracker demo media links removed from docs (assets were never committed).

### Changed
- Documentation project URL points at the GitHub `docs/` tree (Pages hosts the tracker, not MkDocs).
- Legacy `cngx gate` defaults to the mock adapter (parity with `cngx check`); prefer `cngx check`.
- Removed unwired `cngx enforce` CLI and unused Postgres storage backend.
- Demo/example copy aligned with verification-gate positioning (dropped firewall branding).
- `demo_contract.yaml` moved under `examples/contracts/`.

### Added
- Docs for `--evidence-file` in the CLI reference, GitHub Action guide, and coding-agent gate guide.
- When `--evidence-file` passes, the first concrete result line is injected into the gated text so agents that reasoned well but omitted pasting pytest output can still satisfy required patterns.
- `mkdocs build --strict` CI job.

## [0.1.4] - 2026-07-10

### Fixed
- **`cngx watch` crash**: Typer `OptionInfo` defaults leaked into `run_watch`, raising `AttributeError` before the proxy bound.
- Gemini adapter now accepts `GEMINI_API_KEY` as well as `GOOGLE_API_KEY`.
- Default Gemini model switched to `gemini-flash-latest` (`gemini-2.5-flash` is blocked for many new keys).
- `basic_reasoning.yaml` no longer fails concise correct answers solely for length under 20.

### Changed
- PyPI classifier set to **Alpha** (was incorrectly Production/Stable).
- Removed unused SaaS-era extras: `cloud`, `platform`, `postgres`.
- README doc links use absolute GitHub URLs so they work on PyPI.
- Coding-agent strict policy requires result-shaped evidence (`N passed` / `PASSED`), not only the word "test".
- Prometheus metric names renamed from `rvc_*` to `cngx_*`; org/webhook gauges removed.
- Package metadata description aligned with the coding-agent verification pitch.

### Added
- **`--evidence-file`**: offline `cngx check` can cross-check a real pytest/CI log for concrete result lines (`N passed`), raising the bar above narrative claims alone.
- Honest README note: offline text policies can be gamed by fabricated test claims; pair with CI artifacts for proof.

## [0.1.3] - 2026-07-10

### Added
- **Offline policy gate**: `cngx check --output-file`, `--stdin`, and `--response-file` fingerprint existing agent output with no LLM adapter call.
- **Coding-agent policies**: `examples/contracts/coding_agent_verification.yaml` (strict) and `coding_agent_verification_lenient.yaml`.
- **GitHub Action** `output-file` input and `example-agent-gate.yml` workflow.
- **Guide**: [Gate a coding agent in CI](docs/guides/gate-coding-agent.md).

### Fixed
- Semantic drift PC1 projection used the wrong SVD axis (`u[:, 0]` instead of `vt[0]`), breaking `compare_current_text` on 384-dim embeddings.

## [0.1.2] - 2026-07-09

### Changed
- PyPI releases now publish via GitHub Actions OIDC trusted publishing (no stored API token).

## [0.1.1] - 2026-07-08

### Added
- Tracker submit endpoint and live community data fetch.

## [0.1.0] - 2026-07-06

### Changed
- Fresh public relaunch under the name **cngx** (from the private `rvc` package).
- Version reset to 0.1.0 for the open-source developer tool.
- Enterprise/SaaS surfaces removed from the public tree.

### Removed
- Cloud platform CLI commands, enterprise SDK tests, and multi-service `docker-compose.yml` from the public tree.
