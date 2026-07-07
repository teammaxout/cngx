# Installation

Cogscope requires **Python 3.10+** for pip/pipx installs. Standalone release binaries do not require Python.

## Recommended: pipx

[pipx](https://pipx.pypa.io/) installs Cogscope into an isolated environment and puts `cogscope` on your PATH. You do not need to create or manage a virtualenv.

```bash
pipx install cogscope
cogscope version
cogscope quickstart
```

Upgrade later:

```bash
pipx upgrade cogscope
```

## Alternative: pip (project virtualenv)

Use this when you want Cogscope inside a specific project environment:

```bash
pip install cogscope
cogscope version
```

Expected output:

```
Cogscope v0.1.0
```

## Alternative: standalone binary (no Python)

On each [GitHub Release](https://github.com/aadi-joshi/cogscope/releases), CI attaches platform binaries built with PyInstaller:

| Asset | Platform |
|-------|----------|
| `cogscope-linux-x86_64` | Linux x86_64 |
| `cogscope-macos-arm64` | macOS Apple Silicon |
| `cogscope-windows-x86_64.exe` | Windows x86_64 |

```bash
# Linux / macOS
chmod +x cogscope-linux-x86_64
./cogscope-linux-x86_64 quickstart

# Windows
cogscope-windows-x86_64.exe quickstart
```

## From source (development)

```bash
git clone https://github.com/aadi-joshi/cogscope.git
cd cogscope
pip install -e ".[dev]"
```

## Optional provider extras

Only install these if you need live calls to that provider (proxy or capture):

```bash
pipx inject cogscope "google-genai>=1.0.0"    # Gemini, or: pip install "cogscope[gemini]"
pipx inject cogscope "anthropic>=0.30.0"      # Claude, or: pip install "cogscope[claude]"
```

OpenAI support is included in the base package. For pip installs:

```bash
pip install "cogscope[gemini]"
pip install "cogscope[claude]"
```

## Initialize a project directory

Creates `.cogscope/` with a local DuckDB database:

```bash
cogscope init --yes
```

Non-interactive installs use mock adapter defaults. Run without `--yes` in a terminal for an interactive setup wizard.

## Verify installation

```bash
cogscope --help
cogscope quickstart
```

`quickstart` needs no API keys and completes in under 30 seconds. The full CLI/proxy workflow (`watch`, `wrap`, `pin`, `diff`, `check`) works with pipx, pip, or a standalone binary. **Docker is not required.**

## Docker (optional, not default)

A minimal image runs **only the local proxy**, for people who specifically want to containerize on a home server or VPS. This is not part of the normal install path:

```bash
docker build -t cogscope-proxy .
docker run -p 8642:8642 -e OPENAI_API_KEY=sk-... cogscope-proxy
```

See the [Dockerfile](https://github.com/aadi-joshi/cogscope/blob/main/Dockerfile) header comments for details.

## Next steps

- [Quickstart](quickstart.md), see the core value proposition in one command
- [Wrap your agent](../guides/wrap-agent.md), zero-code proxy instrumentation
- [CLI Reference](../cli/reference.md), full command list
