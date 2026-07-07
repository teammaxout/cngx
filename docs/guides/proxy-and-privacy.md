# The Proxy and Your Privacy

Cogscope is **local-first**. This page states exactly what is stored, what is transmitted, and what never leaves your machine.

## The local proxy

`cogscope watch` starts an ASGI reverse proxy (default `http://127.0.0.1:8642`) that:

1. Accepts OpenAI-compatible (`/v1/chat/completions`) and Anthropic-shaped (`/v1/messages`) requests
2. Forwards them to the real provider with your API key from the environment
3. Streams the response back **without added latency**
4. Fingerprints a **copy** of the completed response in the background

Implementation: `cogscope/proxy/`

### API keys

| Concern | Behavior |
|---------|----------|
| Where keys live | Environment variables only (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) |
| Persistence | **Never** written to DuckDB, config files, or logs |
| Lifetime | In memory for the duration of a single forwarded request |
| Telemetry | **None** — no phone-home, no analytics |

## What is stored locally

Default location: `.cogscope/` in your project directory (or path from `COGSCOPE_STORAGE_DIR`).

| File | Contents |
|------|----------|
| `cogscope.db` | DuckDB: traces (prompt + output text), fingerprints (numeric metrics), baselines, diffs |
| `config.json` | Local adapter defaults from `cogscope init` |

Traces contain full prompt and response text **on your disk only**. This is required for fingerprinting and policy checks on your machine. Encrypt or restrict filesystem access if your prompts are sensitive.

## What leaves your machine

**By default: nothing.**

The only exception is **`cogscope submit`**, which is opt-in and requires:

1. `--dry-run` preview showing the exact JSON, or
2. Interactive confirmation (`--yes` to skip)

Submitted payloads contain **only**: model name, timestamp, numeric metrics, drift score, and your baseline label. No prompts, outputs, trace IDs, or task names. Verified by `tests/unit/test_submit_privacy.py`.

If `gh` CLI is available, submit opens a PR to add one JSON file under `tracker/data/community/`. Otherwise it writes to `tracker/data/community/pending/` with manual PR instructions.

## Docker

The optional Dockerfile runs the proxy only — single container, no multi-service stack. You supply API keys at `docker run` time via `-e`.

## Related

- [SECURITY.md](https://github.com/aadi-joshi/cogscope/blob/main/SECURITY.md) — vulnerability reporting
- [Public Drift Log](public-drift-log.md) — what submit shares
