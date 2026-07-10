# CLI Reference

All commands verified against `cngx v0.2.0`. Run `cngx --help` for the live list.

The flagship command is [`verify`](#verify). The proxy and policy commands below (`wrap`, `watch`, `pin`, `diff`, `check`) are advanced.

## Global

```bash
cngx --help
cngx version
```

## verify

Run the checks the agent claimed it ran, compare the claim to reality, and block the merge when they disagree. This is the flagship command.

```bash
cngx verify --output-file agent_message.md -- pytest
```

cngx runs the command after `--`, reads what the agent claimed, and BLOCKS (exit 1) when the agent claimed success but the checks fail, or when the agent's reported test counts do not match the real run. The verdict is bound to real command output, so it cannot be satisfied by prose alone.

**Claim source** (what the agent said), pick one:

```bash
cngx verify --output-file agent_message.md -- pytest   # read claim from a file
cngx verify --stdin -- pytest                          # read claim from stdin
cngx verify --claim "all tests pass, ready to merge" -- pytest
```

**Reality source** (what actually happened), pick one:

```bash
cngx verify --output-file agent_message.md -- pytest -q   # run a command
cngx verify --output-file agent_message.md --evidence-file pytest.log   # parse an existing log
```

Use either a command after `--` or `--evidence-file`, not both.

Example BLOCKED output:

```
BLOCKED  Agent claimed the work is done, but verification failed.
  Agent said: "all tests pass", "ready to merge"
  Real result: FAILED (failures=2)
exit code: 1
```

| Flag | Description |
|------|-------------|
| `-o`, `--output-file` | File with the agent's message; the claim is read from it |
| `--stdin` | Read the agent claim from stdin |
| `-C`, `--claim` | Inline agent claim text |
| `-e`, `--evidence-file` | Parse an existing test/CI log instead of running a command |
| `--require-claim` | Also block if checks pass but the agent made no verification claim |
| `--timeout` | Seconds before the command is killed (default `600`) |
| `-j`, `--json` | Machine-readable verdict |

Exit codes: **0** verified, **1** blocked, **2** usage error.

Supported result parsers: pytest, unittest, jest/vitest, go test, cargo test, and a generic exit-code fallback for any other command. The overall pass/fail comes from the process exit code; parsed counts refine the receipt and catch a claim that contradicts the real numbers.

## init

Initialize `.cngx/` and local DuckDB storage. Only needed for the advanced proxy and policy commands, not for `verify`.

```bash
cngx init --yes
cngx init --force    # overwrite existing
```

## quickstart

Zero-key demo of `cngx verify`. Builds a throwaway project with a real bug, runs the actual tests, shows a false claim blocked and a real fix verified.

```bash
cngx quickstart
```

Completes in about a second. No API keys.

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

!!! note "Advanced, heuristic"
    `check` scores the *text* of agent output against a YAML policy using regex heuristics. It does not run anything, so a fabricated "all tests passed" claim can satisfy a text-only policy. For real proof that the checks pass, use [`cngx verify`](#verify), which is bound to actual command output. Keep `check` for behavioral linting, not proof of execution.

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
