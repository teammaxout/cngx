# CLI Reference

All commands verified against `cngx v0.1.7`. Run `cngx --help` for the live list.

## Global

```bash
cngx --help
cngx version
```

## init

Initialize `.cngx/` and local DuckDB storage.

```bash
cngx init --yes
cngx init --force    # overwrite existing
```

## quickstart

Zero-key demo of silent reasoning regression caught by policy check.

```bash
cngx quickstart
```

Completes in ~0.5 to 1s. Shows BLOCKED policy result.

## wrap

Zero-code instrumentation for an existing agent CLI. Starts the proxy if needed and injects provider base URL env vars into the child process.

```bash
cngx wrap -- aider
cngx wrap -- python my_agent.py
cngx wrap --port 8642 --session-id long-run -- claude
cngx wrap --no-start-proxy -- aider   # fail if proxy not already up
```

Sets `OPENAI_BASE_URL`, `OPENAI_API_BASE`, and `ANTHROPIC_BASE_URL` to the local proxy. See [Wrap your agent](../guides/wrap-agent.md).

## watch

Start local proxy + live terminal dashboard.

```bash
cngx watch
cngx watch --port 8642 --host 127.0.0.1
```

Prints proxy URL (default `http://127.0.0.1:8642`). Use when you want the TUI alongside `wrap`, or when configuring a client manually. Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in the environment.

## pin

Pin the latest capture as a named baseline.

```bash
cngx pin --label baseline
cngx pin --label baseline --trace TRACE_ID
```

## diff

Compare recent captures against a pinned baseline.

```bash
cngx diff
cngx diff --baseline baseline --limit 5
```

Without a pinned baseline, exits with a message to run `pin` first.

## check

Check a prompt or existing agent output against a YAML policy. CI-friendly exit codes.

**Online (default):** capture a new model response, then gate it.

```bash
cngx check -c examples/contracts/basic_reasoning.yaml \
  "What is 2+2? Show your work." \
  --adapter mock --model mock-model
```

**Offline:** fingerprint and gate agent output that already exists. No provider calls.

```bash
cngx check -c examples/contracts/coding_agent_verification.yaml \
  -p "Fix the pagination bug and run tests" \
  --output-file agent_output.txt

cat agent_output.txt | cngx check -c policy.yaml -p "Fix bug" --stdin
```

**Offline with evidence:** also require a real pytest/CI log (must contain e.g. `N passed`):

```bash
cngx check -c examples/contracts/coding_agent_verification.yaml \
  -p "Fix the pagination bug and run tests" \
  --output-file agent_output.txt \
  --evidence-file pytest.log
```

| Flag | Description |
|------|-------------|
| `-c`, `--policy` | Policy YAML path (required) |
| `-p`, `--prompt` | Task prompt when not passed positionally |
| `--prompt-file` | Task prompt context file (stored on trace, not sent to any API) |
| `--output-file` | Agent output file for offline gating |
| `--stdin` | Read agent output from stdin for offline gating |
| `--evidence-file` | CI/test log to cross-check (offline only; must contain e.g. `N passed`). Valid logs inject the first result line into the gated text before the policy check |
| `-m`, `--model` | Model name label (default `mock-model` online, `agent-output` offline) |
| `-a`, `--adapter` | `mock`, `openai`, `gemini`, `claude` (online capture only) |
| `-t`, `--task` | Task ID for capture |
| `-j`, `--json` | JSON output |

Exit codes: **0** pass, **1** blocked, **2** failed.

## regression

Run a fixed benchmark suite with McNemar or paired permutation tests (CI). Requires a YAML suite and policy; optional baseline outcomes JSON for paired stats.

```bash
cngx regression --suite examples/regression_suite_real.yaml \
  --policy examples/contracts/strict_verification.yaml \
  --adapter mock --model mock-model

cngx regression -s examples/regression_suite_real.yaml \
  -c examples/contracts/strict_verification.yaml \
  --baseline-outcomes baseline_scores.json --json
```

| Flag | Description |
|------|-------------|
| `-s`, `--suite` | YAML benchmark suite (required) |
| `-c`, `--policy` | Policy YAML (required) |
| `--baseline-outcomes` | JSON with baseline `correct[]` vector for McNemar |
| `-m`, `--model` | Model name (default `mock-model`) |
| `-a`, `--adapter` | Capture adapter (default `mock`) |
| `-j`, `--json` | JSON output |

See [Drift Detection](../concepts/drift.md#ci-regression-path-paired-benchmarks-with-oracle).

## report

Drift summary over a time window.

```bash
cngx report
cngx report --hours 48 --baseline baseline
cngx report --output drift.html
```

## submit

Submit opt-in drift metrics to the community tracker.

```bash
cngx submit --baseline my-baseline --dry-run
cngx submit --baseline my-baseline
```

Shows exact JSON preview; requires confirmation unless `--yes`. Never includes prompt or output text. Posts to the public tracker API (no GitHub account). No personal identity is collected or stored. See [Public Drift Log](../guides/public-drift-log.md).

## status

Local database statistics.

```bash
cngx status
```

## Legacy / advanced groups

Still available for power users:

| Group | Purpose |
|-------|---------|
| `cngx gate` | Legacy policy commands |
| `cngx capture` | Direct trace capture |
| `cngx drift` | Advanced drift analysis |
| `cngx demo` | System pipeline scenarios |
| `cngx history` | Trace history |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CNGX_PROXY_HOST` | Proxy bind host (default `127.0.0.1`) |
| `CNGX_PROXY_PORT` | Proxy port (default `8642`) |
| `OPENAI_API_KEY` | Forward OpenAI traffic through the local proxy |
| `ANTHROPIC_API_KEY` | Forward Anthropic traffic through the local proxy |
| `GOOGLE_API_KEY` | Gemini **capture adapter** for `cngx check` / `cngx capture` (not used by the local proxy) |

API keys are read from the environment for forwarding or adapter capture only, never logged or written to DuckDB.
