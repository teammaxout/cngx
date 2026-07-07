# CLI Reference

All commands verified against `cogscope v0.1.0`. Run `cogscope --help` for the live list.

## Global

```bash
cogscope --help
cogscope version
```

## init

Initialize `.cogscope/` and local DuckDB storage.

```bash
cogscope init --yes
cogscope init --force    # overwrite existing
```

## quickstart

Zero-key demo of silent reasoning regression caught by policy check.

```bash
cogscope quickstart
```

Completes in ~0.5–1s. Shows BLOCKED policy result.

## watch

Start local proxy + live terminal dashboard.

```bash
cogscope watch
cogscope watch --port 8642 --host 127.0.0.1
```

Prints proxy URL (default `http://127.0.0.1:8642`). Point your app's OpenAI-compatible client at this URL. Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in the environment.

## pin

Pin the latest capture as a named baseline.

```bash
cogscope pin --label baseline
cogscope pin --label baseline --trace TRACE_ID
```

## diff

Compare recent captures against a pinned baseline.

```bash
cogscope diff
cogscope diff --baseline baseline --limit 5
```

Without a pinned baseline, exits with a message to run `pin` first.

## check

Check a prompt against a YAML policy. CI-friendly exit codes.

```bash
cogscope check -c examples/contracts/basic_reasoning.yaml \
  "What is 2+2? Show your work." \
  --adapter mock --model mock-model
```

| Flag | Description |
|------|-------------|
| `-c`, `--policy` | Policy YAML path (required) |
| `-m`, `--model` | Model name (default `mock-model`) |
| `-a`, `--adapter` | `mock`, `openai`, `gemini`, `claude` |
| `-t`, `--task` | Task ID for capture |
| `-j`, `--json` | JSON output |

Exit codes: **0** pass, **1** blocked, **2** failed.

## report

Drift summary over a time window.

```bash
cogscope report
cogscope report --hours 48 --baseline baseline
cogscope report --output drift.html
```

## submit

Submit anonymized drift metrics to the public tracker (opt-in).

```bash
cogscope submit --baseline my-baseline --dry-run
cogscope submit --baseline my-baseline
```

Shows exact JSON preview; requires confirmation unless `--yes`. Never includes prompt or output text. See [Public Drift Log](../guides/public-drift-log.md).

## status

Local database statistics.

```bash
cogscope status
```

## Legacy / advanced groups

Still available for power users:

| Group | Purpose |
|-------|---------|
| `cogscope gate` | Legacy policy commands |
| `cogscope capture` | Direct trace capture |
| `cogscope drift` | Advanced drift analysis |
| `cogscope demo` | System pipeline scenarios |
| `cogscope history` | Trace history |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `COGSCOPE_PROXY_HOST` | Proxy bind host (default `127.0.0.1`) |
| `COGSCOPE_PROXY_PORT` | Proxy port (default `8642`) |
| `OPENAI_API_KEY` | Forward OpenAI traffic |
| `ANTHROPIC_API_KEY` | Forward Anthropic traffic |
| `GOOGLE_API_KEY` | Gemini adapter / proxy |

API keys are read from the environment for forwarding only — never logged or written to DuckDB.
