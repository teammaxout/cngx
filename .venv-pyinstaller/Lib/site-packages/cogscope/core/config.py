"""Configuration management for Cogscope."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class StorageConfig(BaseModel):
    """Configuration for data storage."""

    type: str = "duckdb"  # duckdb or sqlite
    path: Path = Field(default_factory=lambda: Path("cogscope.db"))
    backup_enabled: bool = True
    backup_interval_hours: int = 24


class CaptureConfig(BaseModel):
    """Configuration for trace capture."""

    default_adapter: str = "openai"
    capture_reasoning_tokens: bool = True
    max_trace_size_mb: float = 10.0
    auto_fingerprint: bool = True


class DriftConfig(BaseModel):
    """Configuration for drift detection."""

    window_size: int = 100  # Number of traces to consider
    significance_threshold: float = 0.05  # p-value threshold
    drift_score_threshold: float = 0.3  # Score above this = drift detected
    alert_on_critical: bool = True


class OtelConfig(BaseModel):
    """Optional OpenTelemetry OTLP export (off by default)."""

    enabled: bool = False
    endpoint: str = "http://localhost:4318"
    service_name: str = "cogscope-proxy"


class ServerConfig(BaseModel):
    """Configuration for the optional web server."""

    host: str = "127.0.0.1"
    port: int = 8642
    reload: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class CogscopeConfig(BaseSettings):
    """Main Cogscope configuration."""

    # Project
    project_name: str = "cogscope"
    project_root: Path = Field(default_factory=lambda: Path.cwd())
    cogscope_dir: Path = Field(default_factory=lambda: Path(".cogscope"))

    # Sub-configs
    storage: StorageConfig = Field(default_factory=StorageConfig)
    capture: CaptureConfig = Field(default_factory=CaptureConfig)
    drift: DriftConfig = Field(default_factory=DriftConfig)
    otel: OtelConfig = Field(default_factory=OtelConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    # LLM defaults
    default_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, alias="OPENAI_BASE_URL")

    # Logging
    log_level: str = "INFO"
    log_file: Optional[Path] = None

    model_config = {
        "env_prefix": "COGSCOPE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_cogscope_path(self) -> Path:
        """Get the full path to the .cogscope project directory."""
        return self.project_root / self.cogscope_dir

    def get_db_path(self) -> Path:
        """Get the full path to the database file."""
        return self.get_cogscope_path() / self.storage.path

    def ensure_cogscope_dir(self) -> Path:
        """Ensure the .cogscope directory exists."""
        cogscope_path = self.get_cogscope_path()
        cogscope_path.mkdir(parents=True, exist_ok=True)
        return cogscope_path


# Global config instance
_config: Optional[CogscopeConfig] = None


def get_config(project_root: Optional[Path] = None) -> CogscopeConfig:
    """Get or create the global Cogscope configuration."""
    global _config
    if _config is None:
        if project_root:
            _config = CogscopeConfig(project_root=project_root)
        else:
            _config = CogscopeConfig()
    return _config


def reset_config() -> None:
    """Reset the global config (useful for testing)."""
    global _config
    _config = None


def load_config_from_file(config_path: Path) -> CogscopeConfig:
    """Load configuration from a YAML/JSON file."""
    import json

    if config_path.suffix == ".json":
        with open(config_path) as f:
            data = json.load(f)
    elif config_path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for YAML config files: pip install pyyaml")
        with open(config_path) as f:
            data = yaml.safe_load(f)
    else:
        raise ValueError(f"Unsupported config format: {config_path.suffix}")

    return CogscopeConfig(**data)
