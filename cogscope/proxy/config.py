"""Proxy configuration."""

import os
from dataclasses import dataclass


@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 8642
    default_task_id: str = "proxy"

    @classmethod
    def from_env(cls) -> "ProxyConfig":
        return cls(
            host=os.getenv("COGSCOPE_PROXY_HOST", "127.0.0.1"),
            port=int(os.getenv("COGSCOPE_PROXY_PORT", "8642")),
            default_task_id=os.getenv("COGSCOPE_PROXY_TASK_ID", "proxy"),
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


_config: ProxyConfig | None = None


def get_proxy_config() -> ProxyConfig:
    global _config
    if _config is None:
        _config = ProxyConfig.from_env()
    return _config
