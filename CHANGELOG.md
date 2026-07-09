# Changelog

All notable changes to cngx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-07-09

### Changed
- PyPI releases now publish via GitHub Actions OIDC trusted publishing (no stored API token).

## [0.1.0] - 2026-07-06

### Changed
- **Fresh public relaunch** under the name **cngx** (renamed from the private `rvc` package).
- Prior package name on GitHub and PyPI was renamed to **cngx**.
- **Version reset to 0.1.0**, new version scheme for the open-source developer tool; supersedes the prior 1.0.0/2.0.0 mismatch in the private tree.
- Enterprise/SaaS surfaces (`platform/`, `cloud/`, `sdk/`, `rvc-demo/`, `rvc-prod/`) moved to `_archive_pre_oss/`.
- Deferred modules (correctness, robustness, governance, benchmarks, etc.) archived for future releases.

### Removed
- Cloud platform CLI commands, enterprise SDK tests, and multi-service `docker-compose.yml` from the public tree.

## [1.0.0] - 2026-02-11

### Added
- **Claude/Anthropic adapter**, full support for Claude Opus, Sonnet, Haiku (3, 3.5, 4) with extended thinking extraction
- **RBAC role system**, admin, member, viewer roles with scope-based enforcement
- **Webhook notifications**, real-time alerts on gate blocks, drift detection, contract violations
- **Batch enforcement API**, validate multiple prompts/fingerprints in a single API call
- **Structured JSON logging**, production-grade log output with correlation IDs, compatible with ELK/Datadog
- **Prometheus metrics**, `/metrics` endpoint with enforcement counters, latency histograms, active org gauges
- **PostgreSQL support**, cloud database can use PostgreSQL for horizontal scaling via `CNGX_DATABASE_URL`
- **Streaming capture**, capture reasoning traces from streaming LLM responses
- **GitHub Actions CI/CD**, automated testing, linting, and PyPI publishing on release
- **MkDocs documentation site**, comprehensive docs with tutorials, API reference, contract authoring guide
- **LICENSE file** (MIT)
- **CHANGELOG.md**
- **CONTRIBUTING.md**

### Changed
- **Version bumped to 1.0.0**, production-ready release
- **Cloud auth hardened**, API keys removed from query strings, secure cookie-based web UI auth
- **Rate limiter**, configurable per org plan tier (free: 100/min, team: 500/min, enterprise: 2000/min)
- **pyproject.toml**, updated with all new optional dependencies, proper classifiers
- **CLI error handling**, all commands wrapped with structured error reporting

### Fixed
- API key revoke now uses correct `AuditAction.API_KEY_REVOKE` instead of reusing `API_KEY_CREATE`
- Cloud login page now uses Jinja2 template instead of inline HTML
- Adapters `__init__.py` exports all adapters (was missing GeminiAdapter)
- Circuit breaker in SDK client is now class-level (shared across instances)

### Security
- ReDoS regex sandbox hardened with additional pattern detection
- API keys never appear in server logs or query strings
- Web UI auth uses HttpOnly secure cookies instead of URL parameters
- TLS enforcement flag added to cloud server config

## [0.2.0] - 2025-12-01

### Added
- Cloud platform (multi-tenant SaaS)
- Contract enforcement engine
- Behavioral fingerprinting (30+ metrics)
- DuckDB storage
- OpenAI and Gemini adapters
- CLI with gate, capture, diff, drift, eval, pin commands
- System demo module
- Cross-model validation
- Calibration profiles for 12 model families
- Explainability engine
- Remediation engine

## [0.1.0] - 2025-09-01

### Added
- Initial release
- Core reasoning trace capture
- Basic fingerprinting
- Diff engine
- CLI scaffolding
