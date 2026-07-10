# The Proxy and Your Privacy

cngx is **local-first**. This page states exactly what is stored, what is transmitted, and what never leaves your machine.

## Recommended: `cngx wrap`

For autonomous agent CLIs, prefer:

```bash
cngx wrap -- aider
```

This starts the proxy if needed and sets `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` in the child process. See [Wrap your agent](wrap-agent.md).

Manual base URL configuration remains for tools that ignore env overrides.

## The local proxy

`cngx watch` starts an ASGI reverse proxy (default `http://127.0.0.1:8642`) that:

1. Accepts OpenAI-compatible (`/v1/chat/completions`) and Anthropic-shaped (`/v1/messages`) requests
2. Forwards them to the real provider with your API key from the environment
3. Streams the response back through one local hop (proxy on loopback)
4. Fingerprints a **copy** of the completed response in the background after the response completes

Provider coverage today (honest limits):

| Route | Forwarded | Fingerprinted |
|-------|-----------|---------------|
| OpenAI `/v1/chat/completions` | Yes | Yes (including streaming) |
| Anthropic `/v1/messages` | Yes | No (forward-only; analysis skips non-OpenAI) |
| Gemini | No proxy route | Use `cngx check` / capture adapters instead |

Implementation: `cngx/proxy/`

### API keys

| Concern | Behavior |
|---------|----------|
| Where keys live | Environment variables only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) |
| Persistence | **Never** written to DuckDB, config files, or logs |
| Lifetime | In memory for the duration of a single forwarded request |
| Telemetry | **None**, no phone-home, no analytics |

## What is stored locally

Default location: `.cngx/` in your project directory (or path from `CNGX_STORAGE_DIR`).

| File | Contents |
|------|----------|
| `cngx.db` | DuckDB: traces (prompt + output text), fingerprints (numeric metrics), baselines, diffs |
| `config.json` | Local adapter defaults from `cngx init` |

Traces contain full prompt and response text **on your disk only**. This is required for fingerprinting and policy checks on your machine. Encrypt or restrict filesystem access if your prompts are sensitive.

## What leaves your machine

**By default: nothing.**

The only exception is **`cngx submit`**, which is opt-in and requires:

1. `--dry-run` preview showing the exact JSON, or
2. Interactive confirmation (`--yes` to skip)

Submitted payloads contain **only**: model name, timestamp, numeric metrics, drift score, and your baseline label. No prompts, outputs, trace IDs, or task names. Verified by `tests/unit/test_submit_privacy.py`.

`cngx submit` POSTs to a public HTTPS endpoint after you confirm. No GitHub account is required. No personal identity is collected or stored anywhere in the pipeline.

## Docker

The optional Dockerfile runs the proxy only, single container, no multi-service stack. You supply API keys at `docker run` time via `-e`.

## Related

- [SECURITY.md](https://github.com/aadi-joshi/cngx/blob/main/SECURITY.md) for vulnerability reporting
- [Public Drift Log](public-drift-log.md), what submit shares
