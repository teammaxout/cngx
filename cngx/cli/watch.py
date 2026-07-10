"""cngx watch, proxy + live TUI."""

from __future__ import annotations

import threading
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8642
DEFAULT_OTEL_ENDPOINT = "http://localhost:4318"


def run_watch(
    port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    session_id: Optional[str] = None,
    semantic: bool = False,
    otel: bool = False,
    otel_endpoint: str = DEFAULT_OTEL_ENDPOINT,
) -> None:
    """Start local proxy and live dashboard.

    Plain Python defaults so this can be called from ``main.watch`` without
    Typer OptionInfo objects leaking into runtime.
    """
    from cngx.core.config import get_config
    from cngx.observability.otel import configure_otel
    from cngx.proxy.analysis import set_semantic_analysis_enabled
    from cngx.proxy.config import ProxyConfig
    from cngx.proxy.server import run_proxy
    from cngx.tui.dashboard import run_dashboard

    set_semantic_analysis_enabled(semantic)

    if otel:
        try:
            configure_otel(enabled=True, endpoint=otel_endpoint.rstrip("/"))
        except ImportError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[red]Proxy only binds to localhost for safety.[/]")
        raise typer.Exit(1)

    get_config().ensure_cngx_dir()

    base = f"http://{host}:{port}"
    console.print()
    console.print(
        Panel(
            f"[bold white on blue]  POINT YOUR APP HERE  [/]\n\n"
            f"  OpenAI-compatible base URL:\n"
            f"  [bold cyan]{base}/v1[/]\n\n"
            f"  Example (Python OpenAI SDK):\n"
            f'  [dim]client = OpenAI(base_url="{base}/v1", api_key=os.environ["OPENAI_API_KEY"])[/]\n\n'
            f"  cngx fingerprints traffic locally. API keys stay in memory only.",
            title="[bold]cngx watch[/]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    import cngx.proxy.config as proxy_cfg

    proxy_cfg._config = ProxyConfig(host=host, port=port, default_session_id=session_id)

    proxy_thread = threading.Thread(
        target=run_proxy,
        kwargs={"host": host, "port": port},
        daemon=True,
    )
    proxy_thread.start()

    run_dashboard()
