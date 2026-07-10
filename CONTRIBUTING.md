# Contributing to cngx

Thank you for helping improve cngx. This guide covers local development, code style, and how to extend the project.

## Development setup

### Prerequisites

- Python 3.10+
- Git

### Local install

```bash
git clone https://github.com/aadi-joshi/cngx.git
cd cngx

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -e ".[dev]"
```

Optional provider extras (only if you are working on or testing that adapter):

```bash
pip install -e ".[dev,gemini]"   # Google Gemini
pip install -e ".[dev,claude]"   # Anthropic Claude
```

### Run tests

```bash
pytest                    # full suite
pytest tests/unit/ -q     # unit tests only
pytest tests/unit/test_drift_alerting.py -v   # statistical alerting tests
```

### Lint and format

The repo uses **Ruff** (lint + isort), **Black** (format), and **mypy** (types). Config lives in `pyproject.toml`.

```bash
ruff check .
black --check .
mypy cngx/
```

Auto-format before committing:

```bash
ruff check --fix .
black .
```

Optional: `pre-commit install` if you use pre-commit hooks locally.

## Project layout (active OSS tree)

```
cngx/
├── capture/        # Tracing and LLM adapters
├── proxy/          # Local ASGI reverse proxy
├── tui/            # Live terminal dashboard
├── fingerprint/    # Metric extraction (see metrics.py)
├── diff/           # Trace/fingerprint comparison
├── drift/          # Baseline-relative drift detection
├── calibration/    # Model profiles and adaptive thresholds
├── contracts/      # Behavior policies (YAML) and validation
├── versioning/     # Baseline pinning
├── storage/        # Local DuckDB
├── cli/            # Typer CLI entry points
└── system_demo/    # Reference pipeline scenarios
```

Hosted SaaS and marketing-site code from earlier development is **not** in this repository and is out of scope for new contributions.

## Proposing a new behavioral metric

1. Read `cngx/fingerprint/metrics.py`, `MetricsCalculator` holds regex patterns and counting logic for each signal.
2. Add your metric computation there (keep it fast and deterministic; prefer explicit patterns over NLP).
3. Wire the new field through `cngx/fingerprint/extractor.py` into `BehavioralFingerprint` in `cngx/core/models.py` if it is a new top-level metric.
4. If the metric should influence drift alerting, update `cngx/calibration/profiles.py` (`QUALITY_METRICS` / `LENGTH_METRICS`) and review `cngx/drift/detector.py`.
5. Add unit tests in `tests/unit/test_metrics.py` or `tests/unit/test_fingerprint.py` with a minimal synthetic trace.

Design note: metrics are heuristics. Document what each pattern captures and what it will miss.

## Adding a new LLM provider adapter

1. Create `cngx/capture/adapters/your_provider.py`.
2. Subclass `BaseAdapter` in `cngx/capture/adapters/base.py` and implement:
   - `async def call(...)`, primary async entry point
   - `def call_sync(...)`, synchronous wrapper (often `asyncio.run` or shared core)
   - Streaming via `StreamChunk` if the provider supports it
3. Register the adapter in `cngx/capture/adapters/__init__.py` and in `CngxTracer`’s adapter map (`cngx/capture/tracer.py`).
4. Add routing in `cngx/proxy/app.py` if the proxy should forward that provider’s API shape.
5. Add a model profile stub in `cngx/calibration/profiles.py` if the family has distinct baseline behavior.
6. Add optional dependency in `pyproject.toml` under `[project.optional-dependencies]`.
7. Add tests in `tests/unit/` with mocked HTTP or the `mock` adapter pattern; skip live tests when API keys are absent.

Never log or persist API keys. Read them from environment variables only.

## Pull requests

1. Open an issue or discussion for large changes before investing heavily.
2. Fork, branch from `main` (or the active launch branch), keep PRs focused.
3. Include tests for behavior changes.
4. Run `pytest`, `ruff check .`, `black --check .`, and `mypy cngx/` before opening the PR.
5. Use clear commit messages (`feat:`, `fix:`, `docs:`, etc.).
6. Fill out the PR template; link related issues.

Maintainers review for correctness, test coverage, user-facing clarity (plain language in CLI/docs), and whether new metrics respect the statistical alerting design (no single-metric or length-only false alarms).

## Reporting bugs and suggesting features

- **Bugs:** use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Features:** use the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

## CI integration and README badge

**GitHub Action:** add `uses: aadi-joshi/cngx@v0.1.7` to your workflow. See [docs/guides/github-action.md](docs/guides/github-action.md).

**README badge** (shields.io):

```markdown
[![Monitored by cngx](https://img.shields.io/badge/Monitored%20by-cngx-22c55e?style=flat-square)](https://github.com/aadi-joshi/cngx)
```

More options: [docs/guides/badge.md](docs/guides/badge.md).

Local smoke test for the action logic:

```bash
python scripts/test_github_action_local.py
```

## Demo assets (dev tooling only)

Regenerate README/docs media with scripts under `scripts/demo/`. See `scripts/demo/README.md`.

Terminal quickstart GIF:

```bash
vhs scripts/demo/quickstart.tape
```

Tracker site recording:

```bash
pip install -e ".[dev]"
playwright install chromium
python scripts/demo/record_tracker.py
```

Playwright is listed under `[project.optional-dependencies] dev` only, not in runtime dependencies.


## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be respectful and constructive.

## License

By contributing, you agree your contributions are licensed under the MIT License.
