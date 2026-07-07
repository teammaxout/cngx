"""cogscope watch — proxy + live TUI."""

from __future__ import annotations

import threading

import typer
from rich.console import Console
from rich.panel import Panel

console = Console(stderr=True)


def run_watch(
    port: int = typer.Option(8642, "--port", "-p", help="Local proxy port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (localhost only)"),
) -> None:
    """Start local proxy and live dashboard."""
    from cogscope.core.config import get_config
    from cogscope.proxy.config import ProxyConfig
    from cogscope.proxy.server import run_proxy
    from cogscope.tui.dashboard import run_dashboard

    if host not in ("127.0.0.1", "localhost", "::1"):
        console.print("[red]Proxy only binds to localhost for safety.[/]")
        raise typer.Exit(1)

    get_config().ensure_cogscope_dir()

    base = f"http://{host}:{port}"
    console.print()
    console.print(
        Panel(
            f"[bold white on blue]  POINT YOUR APP HERE  [/]\n\n"
            f"  OpenAI-compatible base URL:\n"
            f"  [bold cyan]{base}/v1[/]\n\n"
            f"  Example (Python OpenAI SDK):\n"
            f"  [dim]client = OpenAI(base_url=\"{base}/v1\", api_key=os.environ[\"OPENAI_API_KEY\"])[/]\n\n"
            f"  Cogscope fingerprints traffic locally. API keys stay in memory only.",
            title="[bold]Cogscope watch[/]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    import cogscope.proxy.config as proxy_cfg

    proxy_cfg._config = ProxyConfig(host=host, port=port)

    proxy_thread = threading.Thread(
        target=run_proxy,
        kwargs={"host": host, "port": port},
        daemon=True,
    )
    proxy_thread.start()

    run_dashboard()
