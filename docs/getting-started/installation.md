# Installation

Cogscope requires **Python 3.10+**.

## From PyPI (recommended)

```bash
pip install cogscope
cogscope version
```

Expected output:

```
Cogscope v0.1.0
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
pip install "cogscope[gemini]"   # Google Gemini
pip install "cogscope[claude]"   # Anthropic Claude
```

OpenAI support is included in the base package.

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

`quickstart` needs no API keys and completes in under 30 seconds.

## Docker (optional)

A minimal image runs **only the local proxy** — for a home server or VPS:

```bash
docker build -t cogscope-proxy .
docker run -p 8642:8642 -e OPENAI_API_KEY=sk-... cogscope-proxy
```

See the [Dockerfile](https://github.com/aadi-joshi/cogscope/blob/main/Dockerfile) header comments for details.

## Next steps

- [Quickstart](quickstart.md) — see the core value proposition in one command
- [CLI Reference](../cli/reference.md) — full command list
