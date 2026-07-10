"""cngx wrap, zero-code proxy instrumentation for agent CLIs."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Optional

import httpx
import typer
from rich.console import Console

from cngx.core.exceptions import CngxError

console = Console(stderr=True)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642
PROXY_START_TIMEOUT_S = 10.0

GEMINI_NOT_PROXIED = (
    "Warning: Gemini traffic is not proxied " "(google-genai ignores base URL env vars)."
)


class ProxyStartError(CngxError):
    """Raised when the local proxy cannot be started or reached."""


def proxy_root_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def is_proxy_healthy(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if the cngx proxy health endpoint responds."""
    try:
        response = httpx.get(
            f"{proxy_root_url(host, port)}/health",
            timeout=timeout,
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        return payload.get("service") == "cngx-proxy"
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def build_wrap_env(
    host: str,
    port: int,
    base_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build child-process env with provider SDK base URLs pointed at cngx."""
    env = dict(base_env or os.environ)
    root = proxy_root_url(host, port)
    openai_base = f"{root}/v1"
    env["OPENAI_BASE_URL"] = openai_base
    # Legacy alias still used by some agent tools and wrappers.
    env["OPENAI_API_BASE"] = openai_base
    env["ANTHROPIC_BASE_URL"] = root
    env["CNGX_PROXY_URL"] = root
    env["CNGX_PROXY_HOST"] = host
    env["CNGX_PROXY_PORT"] = str(port)
    return env


def should_warn_gemini_not_proxied(
    command: list[str],
    env: Optional[dict[str, str]] = None,
) -> bool:
    """True when the child looks Gemini-bound or only Gemini keys are set."""
    env = env if env is not None else dict(os.environ)
    joined = " ".join(command).lower()
    if "gemini" in joined:
        return True
    has_openai = bool(env.get("OPENAI_API_KEY") or env.get("CNGX_OPENAI_API_KEY"))
    has_anthropic = bool(env.get("ANTHROPIC_API_KEY"))
    has_gemini = bool(env.get("GOOGLE_API_KEY") or env.get("GEMINI_API_KEY"))
    return has_gemini and not has_openai and not has_anthropic


def ensure_proxy_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    session_id: Optional[str] = None,
) -> threading.Thread | None:
    """Start the proxy in a daemon thread if it is not already healthy."""
    if is_proxy_healthy(host, port):
        return None

    from cngx.core.config import get_config
    from cngx.proxy.config import ProxyConfig
    from cngx.proxy.server import run_proxy

    get_config().ensure_cngx_dir()

    import cngx.proxy.config as proxy_cfg

    proxy_cfg._config = ProxyConfig(host=host, port=port, default_session_id=session_id)

    thread = threading.Thread(
        target=run_proxy,
        kwargs={"host": host, "port": port},
        daemon=True,
        name="cngx-proxy-wrap",
    )
    thread.start()

    deadline = time.monotonic() + PROXY_START_TIMEOUT_S
    while time.monotonic() < deadline:
        if is_proxy_healthy(host, port):
            return thread
        time.sleep(0.1)

    raise ProxyStartError(
        f"Proxy did not become healthy at {proxy_root_url(host, port)} within "
        f"{PROXY_START_TIMEOUT_S:.0f}s"
    )


def run_wrap(
    command: list[str],
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    session_id: Optional[str] = None,
    no_start_proxy: bool = False,
) -> int:
    """Run command with proxy env injection; start proxy if needed."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[red]Wrap only supports localhost proxy binding for safety.[/]")
        raise typer.Exit(1)

    if not command:
        console.print("[red]Missing command.[/] Example: [cyan]cngx wrap -- python my_agent.py[/]")
        raise typer.Exit(2)

    if no_start_proxy and not is_proxy_healthy(host, port):
        console.print(
            f"[red]Proxy not running at {proxy_root_url(host, port)} "
            f"and --no-start-proxy was set.[/]"
        )
        raise typer.Exit(1)

    try:
        ensure_proxy_running(host=host, port=port, session_id=session_id)
    except ProxyStartError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    env = build_wrap_env(host=host, port=port)
    if should_warn_gemini_not_proxied(command, env):
        console.print(f"[yellow]{GEMINI_NOT_PROXIED}[/]")

    root = proxy_root_url(host, port)
    console.print(
        f"[dim]cngx wrap → {root} "
        f"(OPENAI_BASE_URL={env['OPENAI_BASE_URL']}, "
        f"ANTHROPIC_BASE_URL={env['ANTHROPIC_BASE_URL']})[/]"
    )

    try:
        completed = subprocess.run(command, env=env, check=False)
    except FileNotFoundError:
        console.print(f"[red]Command not found:[/] {command[0]}")
        raise typer.Exit(127) from None

    return int(completed.returncode)


def run_wrap_cli(
    ctx: typer.Context,
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="Proxy port (default 8642)"),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Proxy host (localhost only)"),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Session id for multi-turn tracking",
    ),
    no_start_proxy: bool = typer.Option(
        False,
        "--no-start-proxy",
        help="Require an already-running proxy",
    ),
) -> None:
    """Route an agent CLI through the local proxy. Gemini is not supported."""
    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    raise typer.Exit(
        run_wrap(
            command=command,
            host=host,
            port=port,
            session_id=session_id,
            no_start_proxy=no_start_proxy,
        )
    )
