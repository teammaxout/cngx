"""Run the local proxy server."""

import logging

import uvicorn

from cogscope.proxy.app import create_app
from cogscope.proxy.config import get_proxy_config

logger = logging.getLogger("cogscope.proxy")


def run_proxy(host: str | None = None, port: int | None = None) -> None:
    cfg = get_proxy_config()
    host = host or cfg.host
    port = port or cfg.port
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="warning")
