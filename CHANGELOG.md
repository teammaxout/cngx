# Changelog

All notable changes to cngx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `cngx verify`: `--from-commit [REF]` and `--from-pr` claim sources, reading the agent
  claim from a git commit message or the GitHub Actions PR body. Claim sources are now
  mutually exclusive; passing more than one is a usage error (exit 2).
- `cngx verify`: result parsers for rspec, phpunit, dotnet test / vstest, mocha, and
  Maven Surefire / Gradle output, so parsed pass/fail counts and count-mismatch detection
  now cover those runners in addition to pytest, unittest, jest/vitest, go test, and cargo.

### Changed
- Repository moved to [`maxoutlabs/cngx`](https://github.com/maxoutlabs/cngx).
  Docs, PyPI project URLs, Action examples, and badges now point at the org.
- Org rename settled on [maxoutlabs/cngx](https://github.com/maxoutlabs/cngx).

## [0.2.0] - 2026-07-10

### Added
- **`cngx verify`**: the new flagship. Runs the real check an agent claimed it ran
  (`cngx verify --output-file agent.md -- pytest`), parses the true result, and blocks
  the merge (exit 1) when the agent claimed success but the checks fail, or when its
  reported counts do not match the real run. The verdict is bound to actual command
  output, so it cannot be satisfied by prose.
- Result parsers for pytest, unittest, jest/vitest, go test, cargo test, and generic
  exit-code commands.
- Claim extractor that reads verification assertions from an agent message.
- `cngx verify --evidence-file` to gate an existing CI/test log without executing.

### Changed
- **Repositioned around execution truth.** README, quickstart, and the GitHub Action
  now lead with `verify`. The heuristic text policies (`cngx check`) are demoted to an
  advanced lint and print a pointer to `verify`, because scoring the prose of agent
  output can be gamed by a fabricated "all tests passed" claim.
- `cngx quickstart` now runs real tests in a throwaway project (stdlib unittest, no
  API keys) and shows a false claim being blocked, then a real fix verified.
- GitHub Action gains a `command` input for the verify flow; the legacy `policy` path
  still works.

### Fixed
- Removed the community tracker seed/test records so charts reflect only real submits.

## [0.1.10] - 2026-07-10

### Fixed
- Public tracker no longer plots the same fingerprint twice (vertical chart spikes from dual-baseline submits).
- Submit CLI and Lambda reject duplicate fingerprint shapes.

### Changed
- Sharper honest tagline: CI gate for merge-ready agents that never showed tests.
- README explicitly refuses fake token-savings claims until a circuit breaker exists.
## [0.1.9] - 2026-07-10

### Fixed
- Public tracker no longer shows harness tabs like `cngx-e2e-test` / `cngx-cli-live` (client filter + submit/Lambda denylist).
- `cngx submit` only includes fingerprints that match the baseline model (no cross-model pollution).

### Changed
- Tracker UI: record counts on tabs, clearer status line, less infra jargon in loading copy.
## [0.1.8] - 2026-07-10

### Fixed
- Claude adapter no longer sends both `temperature` and `top_p` (rejected by current Haiku/Sonnet models).
- Windows `cngx diff` no longer crashes on cp1252 consoles (UTF-8 stdio + ASCII change markers).
- Diff recommendations no longer claim "no critical issues" when major/critical metric shifts exist.

### Changed
- Default `haiku` model alias points at `claude-haiku-4-5-20251001`.
## [0.1.7] - 2026-07-10

### Fixed
- Windows release binaries: install the built wheel with bash so `dist/*.whl` expands (PowerShell left deps missing for PyInstaller).
- Treat typer/rich/click as required PyInstaller collections.
## [0.1.6] - 2026-07-10

### Fixed
- Windows PyInstaller binaries: collect `pydantic_core` explicitly, fail the build if required packages are missing, exclude optional ML stacks.
- Package `__init__` is lazy so `--help` / `version` do not import the full dependency graph at startup.

### Changed
- Anthropic `/v1/messages` traffic is fingerprinted (stream and non-stream) like OpenAI.
- `cngx wrap` warns when Gemini is the only configured path (proxy does not route Gemini).

### Added
- SECURITY.md notes Chart.js CDN on the tracker and edge access-log caveats for submit.
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
