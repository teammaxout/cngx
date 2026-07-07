"""cogscope wrap, zero-code proxy instrumentation for agent CLIs."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Optional

import httpx
import typer
from rich.console import Console

from cogscope.core.exceptions import CogscopeError

console = Console(stderr=True)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642
PROXY_START_TIMEOUT_S = 10.0


class ProxyStartError(CogscopeError):
    """Raised when the local proxy cannot be started or reached."""


def proxy_root_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def is_proxy_healthy(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if the Cogscope proxy health endpoint responds."""
    try:
        response = httpx.get(
            f"{proxy_root_url(host, port)}/health",
            timeout=timeout,
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        return payload.get("service") == "cogscope-proxy"
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def build_wrap_env(
    host: str,
    port: int,
    base_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build child-process env with provider SDK base URLs pointed at Cogscope."""
    env = dict(base_env or os.environ)
    root = proxy_root_url(host, port)
    openai_base = f"{root}/v1"
    env["OPENAI_BASE_URL"] = openai_base
    # Legacy alias still used by some agent tools and wrappers.
    env["OPENAI_API_BASE"] = openai_base
    env["ANTHROPIC_BASE_URL"] = root
    env["COGSCOPE_PROXY_URL"] = root
    env["COGSCOPE_PROXY_HOST"] = host
    env["COGSCOPE_PROXY_PORT"] = str(port)
    return env


def ensure_proxy_running(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    session_id: Optional[str] = None,
) -> threading.Thread | None:
    """Start the proxy in a daemon thread if it is not already healthy."""
    if is_proxy_healthy(host, port):
        return None

    from cogscope.core.config import get_config
    from cogscope.proxy.config import ProxyConfig
    from cogscope.proxy.server import run_proxy

    get_config().ensure_cogscope_dir()

    import cogscope.proxy.config as proxy_cfg

    proxy_cfg._config = ProxyConfig(host=host, port=port, default_session_id=session_id)

    thread = threading.Thread(
        target=run_proxy,
        kwargs={"host": host, "port": port},
        daemon=True,
        name="cogscope-proxy-wrap",
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
        console.print(
            "[red]Missing command.[/] Example: [cyan]cogscope wrap -- python my_agent.py[/]"
        )
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
    root = proxy_root_url(host, port)
    console.print(
        f"[dim]Cogscope wrap → {root} "
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
    port: int = typer.Option(DEFAULT_PORT, "--port", "-p", help="Local proxy port"),
    host: str = typer.Option(DEFAULT_HOST, "--host", help="Local proxy host"),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Explicit session id for multi-turn trajectory tracking",
    ),
    no_start_proxy: bool = typer.Option(
        False,
        "--no-start-proxy",
        help="Fail if the proxy is not already running",
    ),
) -> None:
    """Wrap an agent command with zero-code proxy instrumentation."""
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
