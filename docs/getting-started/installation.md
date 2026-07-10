# Installation

cngx requires **Python 3.10+** for pip/pipx installs. Standalone release binaries do not require Python.

## Recommended: pipx

[pipx](https://pipx.pypa.io/) installs cngx into an isolated environment and puts `cngx` on your PATH. You do not need to create or manage a virtualenv.

```bash
pipx install cngx
cngx version
cngx quickstart
```

Upgrade later:

```bash
pipx upgrade cngx
```

## Alternative: pip (project virtualenv)

Use this when you want cngx inside a specific project environment:

```bash
pip install cngx
cngx version
```

Expected output:

```
cngx v0.1.4
```

## Alternative: standalone binary (no Python)

On each [GitHub Release](https://github.com/aadi-joshi/cngx/releases), CI attaches platform binaries built with PyInstaller:

| Asset | Platform |
|-------|----------|
| `cngx-linux-x86_64` | Linux x86_64 |
| `cngx-macos-arm64` | macOS Apple Silicon |
| `cngx-windows-x86_64.exe` | Windows x86_64 |

```bash
# Linux / macOS
chmod +x cngx-linux-x86_64
./cngx-linux-x86_64 quickstart

# Windows
cngx-windows-x86_64.exe quickstart
```

## From source (development)

```bash
git clone https://github.com/aadi-joshi/cngx.git
cd cngx
pip install -e ".[dev]"
```

## Optional provider extras

Only install these if you need live calls to that provider (proxy or capture):

```bash
pipx inject cngx "google-genai>=1.0.0"    # Gemini, or: pip install "cngx[gemini]"
pipx inject cngx "anthropic>=0.30.0"      # Claude, or: pip install "cngx[claude]"
```

OpenAI support is included in the base package. For pip installs:

```bash
pip install "cngx[gemini]"
pip install "cngx[claude]"
```

## Initialize a project directory

Creates `.cngx/` with a local DuckDB database:

```bash
cngx init --yes
```

Non-interactive installs use mock adapter defaults. Run without `--yes` in a terminal for an interactive setup wizard.

## Verify installation

```bash
cngx --help
cngx quickstart
```

`quickstart` needs no API keys and completes in under 30 seconds. The full CLI/proxy workflow (`watch`, `wrap`, `pin`, `diff`, `check`) works with pipx, pip, or a standalone binary. **Docker is not required.**

## Docker (optional, not default)

A minimal image runs **only the local proxy**, for people who specifically want to containerize on a home server or VPS. This is not part of the normal install path:

```bash
docker build -t cngx-proxy .
docker run -p 8642:8642 -e OPENAI_API_KEY=sk-... cngx-proxy
```

See the [Dockerfile](https://github.com/aadi-joshi/cngx/blob/main/Dockerfile) header comments for details.

## Next steps

- [Quickstart](quickstart.md), see the core value proposition in one command
- [Wrap your agent](../guides/wrap-agent.md), zero-code proxy instrumentation
- [CLI Reference](../cli/reference.md), full command list
