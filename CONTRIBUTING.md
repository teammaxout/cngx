# Contributing to cngx

Thanks for helping improve cngx. This guide covers what the project is, how it is laid out, and how to develop against it.

## What cngx is (read this first)

The core of cngx is one command: **`cngx verify`**. It runs the checks an AI coding agent claimed it ran, parses the real result, and blocks the merge when the claim and reality disagree. The verdict is bound to real command output, never to the prose of the agent's message.

Everything else in the tree is an **advanced / experimental** layer that is not the headline: the heuristic policy lint (`cngx check`), the local proxy and session drift (`wrap`, `watch`, `pin`, `diff`), and the community tracker. Contributions to the core carry the most weight.

## Development setup

Requirements: Python 3.10+ and Git.

```bash
git clone https://github.com/maxoutlabs/cngx.git
cd cngx
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Run the demo to confirm your setup:

```bash
cngx quickstart
```

### Tests, lint, format

```bash
pytest                      # full suite
pytest tests/unit/test_verify_parsers.py -q   # the parsers you are most likely to touch
ruff check .
black --check .             # CI formats with target py311; run: black --fast . if you are on 3.10
mypy cngx/                  # advisory, not a hard gate
```

Please add tests for behavior changes and keep the suite green before opening a PR.

## Project layout

```
cngx/
├── verify/         # CORE. runner, result parsers, claim extractor, verdict
├── cli/            # Typer entry points (verify_cmd.py, check_cmd.py, main.py)
├── capture/        # tracing and LLM adapters (advanced: used by check/proxy)
├── fingerprint/    # heuristic metric extraction (advanced)
├── drift/          # baseline-relative drift detection (advanced)
├── proxy/          # local ASGI reverse proxy for wrap/watch (advanced)
├── contracts/      # YAML behavior policies for check (advanced)
├── enforcement/    # evidence-file cross-check and the GitHub Action generator
├── storage/        # local DuckDB
└── tui/            # live terminal dashboard (advanced)
```

Hosted SaaS and marketing-site code from earlier development is not in this repository and is out of scope.

## The most useful place to contribute: result parsers

`cngx verify` is only as good as its ability to read real test-runner output. Parsers live in `cngx/verify/parsers.py`.

To add support for a new runner (for example rspec, phpunit, dotnet test):

1. Add a `_parse_<runner>(text) -> TestResult | None` function. Return `None` when the text is clearly not that runner so the next parser can try.
2. Register it in the `_PARSERS` tuple. Order matters: more specific formats go before the generic pytest count parser.
3. Set `ok` from the real result, and fill `passed` / `failed` / `errors` / `total` and a human `summary_line` when you can. The overall pass/fail from an actual process run always defers to the exit code (see `parse_output`).
4. Add a test with a real captured output snippet in `tests/unit/test_verify_parsers.py`.

Claim extraction (what the agent asserted) lives in `cngx/verify/claims.py`. Precision matters more than recall there: a false "the agent claimed success" produces a wrong verdict, so only add strong, specific assertions. Bind words such as "green" or "passed" to a concrete verification subject (`CI`, checks, tests, or a suite); never treat broad phrases such as "done", "looks good", or "should be fine" as success claims.

## Advanced contributions

- **New behavioral metric (fingerprint):** see `cngx/fingerprint/metrics.py`, wire through `extractor.py` and `core/models.py`, and add tests. Metrics are heuristics; document what each captures and misses. If it affects drift alerting, review `cngx/calibration/profiles.py` (`QUALITY_METRICS` / `LENGTH_METRICS`) and `cngx/drift/detector.py`.
- **New LLM provider adapter:** subclass `BaseAdapter` in `cngx/capture/adapters/base.py`, register it in the adapter map in `cngx/capture/tracer.py`, add proxy routing in `cngx/proxy/app.py` if needed, and add an optional dependency in `pyproject.toml`. Never log or persist API keys; read them from environment variables only.

## Pull requests

1. Open an issue for large changes before investing heavily.
2. Branch from `main`, keep PRs focused, include tests.
3. Run `pytest`, `ruff check .`, and `black --check .` before opening.
4. Use clear, lowercase commit messages (`feat:`, `fix:`, `docs:`) with no em dashes.
5. Fill out the PR template and link related issues.

## CI integration and badge

Use the action in your workflow:

```yaml
- uses: maxoutlabs/cngx@v0.2.0
  with:
    output-file: agent_message.md
    command: pytest -q
```

Local smoke test for the action logic:

```bash
python scripts/test_github_action_local.py
```

## Reporting bugs and suggesting features

- Bugs: [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- Features: [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). Be respectful and constructive.

## License

By contributing, you agree your contributions are licensed under the MIT License.
