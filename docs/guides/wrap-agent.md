# Wrap your agent

Instrument an existing agent CLI through the local proxy with zero code changes. Wrap fingerprints traffic and enables session drift alerts. It does **not** run YAML policy gates; use `cngx check --output-file` (or the GitHub Action) to block merges.

## Basic usage

```bash
cngx init --yes
export OPENAI_API_KEY=sk-...   # or ANTHROPIC_API_KEY, etc.

cngx wrap -- aider
cngx wrap -- claude
cngx wrap -- python my_agent.py
```

What happens:

1. If the cngx proxy is not already running on `127.0.0.1:8642`, `wrap` starts it in the background.
2. `wrap` sets provider SDK environment variables in the **child process only** (your parent shell is unchanged).
3. Your agent runs as usual; traffic is intercepted and fingerprinted locally.

## Environment variables set by `wrap`

| Variable | Value | Used by |
|----------|-------|---------|
| `OPENAI_BASE_URL` | `http://127.0.0.1:8642/v1` | OpenAI Python SDK, many OpenAI-compatible tools |
| `OPENAI_API_BASE` | same as above | Legacy alias still used by some agent wrappers |
| `ANTHROPIC_BASE_URL` | `http://127.0.0.1:8642` | Anthropic Python SDK, Claude Code-style CLIs |
| `CNGX_PROXY_URL` | `http://127.0.0.1:8642` | cngx-specific hint for custom tooling |

Custom port:

```bash
cngx wrap --port 9000 -- aider
```

Session tracking for long runs:

```bash
cngx wrap --session-id refactor-auth -- aider
```

Require an already-running proxy (fail instead of auto-start):

```bash
cngx watch    # terminal 1
cngx wrap --no-start-proxy -- aider    # terminal 2
```

## Google Gemini note

`cngx wrap` cannot proxy Gemini. The official **google-genai** Python SDK does **not** read a base-URL environment variable. If your command mentions `gemini`, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` is the only provider key set, wrap prints a one-line warning and continues (OpenAI/Anthropic env injection still happens for other tools).

For Gemini use `cngx check --adapter gemini` instead. Manual `http_options.base_url` in your own code is possible but unsupported by wrap.

## Live dashboard (optional)

`wrap` does not open the TUI. For a live session view while the agent runs:

```bash
# terminal 1
cngx wrap -- aider

# terminal 2
cngx watch
```

`watch` attaches to the same proxy port and shows turn count, verification health, and drift alerts.

## Fallback: manual base URL

Some tools ignore environment overrides or bake in provider URLs. For those, configure the client explicitly:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8642/v1", api_key=os.environ["OPENAI_API_KEY"])
```

See [Proxy and Privacy](proxy-and-privacy.md) for routing details and key handling.

## What was tested

- **Verified in CI:** `cngx wrap` injects `OPENAI_BASE_URL`, routes a child HTTP client through the local proxy, and persists a captured trace/fingerprint (mock upstream).
- **Not verified in CI:** every third-party agent CLI (Aider, Claude Code, etc.). Those tools are expected to work when they respect the standard SDK env vars above; if yours does not, use manual base URL configuration.

## Related

- [Session trajectories](../concepts/sessions.md)
- [Positioning](../concepts/positioning.md)
- [CLI reference](../cli/reference.md)
